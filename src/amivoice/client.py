"""AmiVoice 高レベルクライアント。HTTP 認識 (transcribe) と WebSocket ストリーミング (stream) を提供する。"""

import os
import threading
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from com.amivoice.hrp.Hrp import Hrp as _Hrp
from com.amivoice.hrp.HrpListener import HrpListener

from ._audio import resolve_audio
from ._billing import resolve_billing_extension
from ._params import UNSET, RecognitionParams, _UnsetType, merge_params
from ._segmenter import SegmenterProperties
from ._stream import StreamConnectionManager
from ._transport import HrpTransport, WrpTransport, bool_string
from ._types import AudioSource
from .exceptions import AuthenticationError, ConfigurationError, ConnectionFailedError, RecognitionError
from .models import RecognitionResult, parse_result

_DEFAULT_HRP_URL: str = "https://acp-api.amivoice.com/v1/recognize"
_DEFAULT_WRP_URL: str = "wss://acp-api.amivoice.com/v1/"


def _construct_hrp_transport() -> HrpTransport:
    """HRP ライブラリのトランスポートを生成する。"""
    return _Hrp.construct()


def _resolve_url(override: str | _UnsetType, default: str) -> str:
    """呼び出し時 URL override が未指定ならインスタンス既定値を返す。"""
    return override if isinstance(override, str) else default


def _resolve_segmenter_properties(
    segmenter: SegmenterProperties | None,
    segmenter_properties: str | None,
) -> str | None:
    """コンストラクタの型付き設定または生文字列を解決する。

    Args:
        segmenter: 型付きセグメンター設定
        segmenter_properties: 既存の生文字列設定

    Returns:
        トランスポートへ渡すセグメンター設定文字列

    Raises:
        ConfigurationError: 両方の設定が指定された場合
    """
    if segmenter is not None and segmenter_properties is not None:
        raise ConfigurationError("segmenter and segmenter_properties cannot be specified together")
    return segmenter.to_parameter() if segmenter is not None else segmenter_properties


def _resolve_segmenter_override(
    segmenter: SegmenterProperties | None | _UnsetType,
    segmenter_properties: str | None | _UnsetType,
) -> str | None | _UnsetType:
    """呼び出し時の型付き segmenter override と生文字列を解決する。

    Args:
        segmenter: 型付きセグメンター設定または未指定 sentinel
        segmenter_properties: 既存の生文字列設定または未指定 sentinel

    Returns:
        トランスポートへ渡すセグメンター設定文字列または未指定 sentinel

    Raises:
        ConfigurationError: 両方の設定が指定された場合
    """
    if not isinstance(segmenter, _UnsetType) and not isinstance(segmenter_properties, _UnsetType):
        raise ConfigurationError("segmenter and segmenter_properties cannot be specified together")
    if isinstance(segmenter, _UnsetType):
        return segmenter_properties
    return segmenter.to_parameter() if segmenter is not None else None


class _HrpListenerAdapter(HrpListener):
    """HRP ライブラリのコールバックを受け取る内部アダプター。

    コールバックのメソッド名は override 元の ``HrpListener``（上流ライブラリ）に合わせる。
    引数名は snake_case にするが、上流はキャメルケースの引数を位置引数で渡すため、
    引数名不一致による ``reportIncompatibleMethodOverride`` を抑制する。
    """

    def __init__(self) -> None:
        super().__init__()
        self.session_id: str | None = None
        self.raw_result: str | None = None
        self.finalized_event = threading.Event()

    def resultCreated(self, session_id: str) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        self.session_id = session_id

    def resultFinalized(self, result: str) -> None:
        self.raw_result = result
        self.finalized_event.set()


class AmiVoiceClient:
    """AmiVoice API の高レベルクライアント。

    HTTP 音声認識 API (HRP) と WebSocket ストリーミング API (WRP) を統一インタフェースで提供する。

    Args:
        api_key: 認証情報。省略時は環境変数 ``AMIVOICE_API_KEY`` を使用する。
        grammar_file_names: 接続エンジン名。
        codec: 音声コーデック（例: ``"16K"``, ``"8K"``）。
        result_type: 認識結果タイプ。
        proxy_server_name: プロキシサーバ名。
        connect_timeout: 接続タイムアウト（ミリ秒）。0 は無制限。
        receive_timeout: 受信タイムアウト（ミリ秒）。0 は無制限。
        mode: 認識モード。
        profile_id: プロファイル ID。
        profile_words: セッション単語登録リスト。
        segmenter_type: セグメンタータイプ。
        segmenter: 発話検出、話者ダイアライゼーション、言語識別の型付き設定。
        segmenter_properties: セグメンター設定。
        keep_filler_token: フィラー単語を出力するか。
        result_updated_interval: 途中結果の発行間隔（ミリ秒）。
        extension: 使用量集計タグ。
        billing_key: 使用量集計タグを専用形式で指定する文字列。
        recognition_timeout: 認識タイムアウト（ミリ秒）。0 は無制限。
        result_encoding: 認識結果の文字エンコーディング（HRP 専用）。
        voice_detection: 発話区間検出パラメータ。
        accept_topic: HTTP ``Accept-Topic`` ヘッダ（HRP 専用）。
        content_type: HTTP ``Content-Type`` ヘッダ（HRP 専用）。
        accept: HTTP ``Accept`` ヘッダ（HRP 専用）。
        domain_id: ドメイン ID（HRP 専用）。
        confidence_level: 発話区間の信頼度しきい値（0.0 以上 1.0 以下）。
        no_input_timeout: 無入力タイムアウト（ミリ秒）（WRP 専用）。
        http_api_url: HRP（HTTP）API エンドポイント URL の既定値。
        ws_api_url: WRP（WebSocket）API エンドポイント URL の既定値。
        hrp_transport: テスト用 HRP トランスポート注入口。
        wrp_transport: テスト用 WRP トランスポート注入口。

    Raises:
        AuthenticationError: ``api_key`` が指定されず環境変数も設定されていない場合。
        ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
            ``extension`` と ``billing_key`` を同時指定した場合。

    Example::

        # HTTP 認識
        client = AmiVoiceClient(
            api_key="...",
            grammar_file_names="-a-general",
            codec="16K",
        )
        result = client.transcribe(
            "audio.wav"
        )
        print(
            result.data[
                "text"
            ]
        )

        # WebSocket ストリーミング
        with (
            client.stream() as session
        ):
            session.write(
                audio_chunk
            )
            for event in session.poll():
                if event.is_final:
                    print(
                        event.result.data[
                            "text"
                        ]
                    )
            session.end()
    """

    def __init__(  # noqa: PLR0913
        self,
        api_key: str | None = None,
        *,
        grammar_file_names: str | None = None,
        codec: str | None = None,
        result_type: str | None = None,
        proxy_server_name: str | None = None,
        connect_timeout: int = 0,
        receive_timeout: int = 0,
        mode: str | None = None,
        profile_id: str | None = None,
        profile_words: str | None = None,
        segmenter_type: str | None = None,
        segmenter: SegmenterProperties | None = None,
        segmenter_properties: str | None = None,
        confidence_level: float | None = None,
        keep_filler_token: bool | None = None,
        result_updated_interval: int | None = None,
        extension: str | None = None,
        billing_key: str | None = None,
        recognition_timeout: int | None = None,
        result_encoding: str | None = None,
        voice_detection: str | None = None,
        accept_topic: str | None = None,
        content_type: str | None = None,
        accept: str | None = None,
        domain_id: str | None = None,
        no_input_timeout: int | None = None,
        http_api_url: str = _DEFAULT_HRP_URL,
        ws_api_url: str = _DEFAULT_WRP_URL,
        hrp_transport: HrpTransport | None = None,
        wrp_transport: WrpTransport | None = None,
    ) -> None:
        """クライアント設定を保持し、未指定時は環境変数から API キーを解決する。"""
        resolved_key = api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY")
        if resolved_key is None:
            raise AuthenticationError("AMIVOICE_API_KEY is not set")

        resolved_segmenter_properties = _resolve_segmenter_properties(segmenter, segmenter_properties)
        self._api_key: str = resolved_key
        self._params = RecognitionParams(
            grammar_file_names=grammar_file_names,
            codec=codec,
            result_type=result_type,
            proxy_server_name=proxy_server_name,
            connect_timeout=connect_timeout,
            receive_timeout=receive_timeout,
            mode=mode,
            profile_id=profile_id,
            profile_words=profile_words,
            segmenter_type=segmenter_type,
            segmenter_properties=resolved_segmenter_properties,
            keep_filler_token=keep_filler_token,
            result_updated_interval=result_updated_interval,
            extension=extension,
            billing_key=billing_key,
            recognition_timeout=recognition_timeout,
            result_encoding=result_encoding,
            voice_detection=voice_detection,
            accept_topic=accept_topic,
            content_type=content_type,
            accept=accept,
            domain_id=domain_id,
            confidence_level=confidence_level,
            no_input_timeout=no_input_timeout,
        )
        self._http_api_url = http_api_url
        self._ws_api_url = ws_api_url
        # テスト注入口
        self._hrp_transport = hrp_transport
        self._wrp_transport = wrp_transport

    # ------------------------------------------------------------------
    # HRP: transcribe()
    # ------------------------------------------------------------------

    def transcribe(  # noqa: PLR0913
        self,
        audio: AudioSource,
        *,
        grammar_file_names: str | None | _UnsetType = UNSET,
        codec: str | None | _UnsetType = UNSET,
        result_type: str | None | _UnsetType = UNSET,
        proxy_server_name: str | None | _UnsetType = UNSET,
        connect_timeout: int | _UnsetType = UNSET,
        receive_timeout: int | _UnsetType = UNSET,
        mode: str | None | _UnsetType = UNSET,
        profile_id: str | None | _UnsetType = UNSET,
        profile_words: str | None | _UnsetType = UNSET,
        segmenter_type: str | None | _UnsetType = UNSET,
        segmenter: SegmenterProperties | None | _UnsetType = UNSET,
        segmenter_properties: str | None | _UnsetType = UNSET,
        confidence_level: float | None | _UnsetType = UNSET,
        keep_filler_token: bool | None | _UnsetType = UNSET,
        result_updated_interval: int | None | _UnsetType = UNSET,
        extension: str | None | _UnsetType = UNSET,
        billing_key: str | None | _UnsetType = UNSET,
        recognition_timeout: int | None | _UnsetType = UNSET,
        result_encoding: str | None | _UnsetType = UNSET,
        voice_detection: str | None | _UnsetType = UNSET,
        accept_topic: str | None | _UnsetType = UNSET,
        content_type: str | None | _UnsetType = UNSET,
        accept: str | None | _UnsetType = UNSET,
        domain_id: str | None | _UnsetType = UNSET,
        raise_on_error: bool = True,
        api_url: str | _UnsetType = UNSET,
    ) -> RecognitionResult:
        """音声を HTTP API に送信し、認識結果を返す。

        接続・切断はこのメソッドが内部で管理する。スレッドセーフ（呼び出しごとに独立した接続を確立する）。
        呼び出し時に指定した設定は、その呼び出しに限ってコンストラクタ時の設定を上書きする。
        引数を省略した場合はインスタンスに保持された同名設定を使用する。

        Args:
            audio: 音声ソース（bytes・バイナリストリーム・ファイルパス）。
            grammar_file_names: 接続エンジン名の呼び出し時 override。
            codec: 音声コーデックの呼び出し時 override。
            result_type: 認識結果タイプの呼び出し時 override。
            proxy_server_name: プロキシサーバ名の呼び出し時 override。
            connect_timeout: 接続タイムアウト（ミリ秒）の呼び出し時 override。
            receive_timeout: 受信タイムアウト（ミリ秒）の呼び出し時 override。
            mode: 認識モードの呼び出し時 override。
            profile_id: プロファイル ID の呼び出し時 override。
            profile_words: セッション単語登録リストの呼び出し時 override。
            segmenter_type: セグメンタータイプの呼び出し時 override。
            segmenter: 型付きセグメンター設定の呼び出し時 override。
            segmenter_properties: セグメンター設定の呼び出し時 override。
            keep_filler_token: フィラー単語出力設定の呼び出し時 override。
            result_updated_interval: 途中結果発行間隔の呼び出し時 override。
            extension: 使用量集計タグの呼び出し時 override。
            billing_key: 使用量集計タグの呼び出し時 override。
            recognition_timeout: 認識タイムアウト（ミリ秒）の呼び出し時 override。
            result_encoding: 認識結果エンコーディングの呼び出し時 override。
            voice_detection: 発話区間検出パラメータの呼び出し時 override。
            accept_topic: HTTP ``Accept-Topic`` ヘッダの呼び出し時 override。
            content_type: HTTP ``Content-Type`` ヘッダの呼び出し時 override。
            accept: HTTP ``Accept`` ヘッダの呼び出し時 override。
            domain_id: ドメイン ID の呼び出し時 override。
            confidence_level: 発話区間の信頼度しきい値（0.0 以上 1.0 以下）の呼び出し時 override。
            raise_on_error: エラー結果の場合に ``RecognitionError`` を送出するか否か。
            api_url: HRP API エンドポイント URL の呼び出し時 override。

        Returns:
            認識結果。

        Raises:
            ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
                ``extension`` と ``billing_key`` を同時指定した場合。
            ConnectionFailedError: AmiVoice API への接続に失敗した場合。
            RecognitionError: 音声認識処理中にエラーが発生した場合。
        """
        resolved_segmenter_properties = _resolve_segmenter_override(segmenter, segmenter_properties)
        params = merge_params(
            self._params,
            grammar_file_names=grammar_file_names,
            codec=codec,
            result_type=result_type,
            proxy_server_name=proxy_server_name,
            connect_timeout=connect_timeout,
            receive_timeout=receive_timeout,
            mode=mode,
            profile_id=profile_id,
            profile_words=profile_words,
            segmenter_type=segmenter_type,
            segmenter_properties=resolved_segmenter_properties,
            keep_filler_token=keep_filler_token,
            result_updated_interval=result_updated_interval,
            extension=extension,
            billing_key=billing_key,
            recognition_timeout=recognition_timeout,
            result_encoding=result_encoding,
            voice_detection=voice_detection,
            accept_topic=accept_topic,
            content_type=content_type,
            accept=accept,
            domain_id=domain_id,
            confidence_level=confidence_level,
        )
        resolved_url = _resolve_url(api_url, self._http_api_url)

        # 注入されたトランスポートでは connect/disconnect を呼ばない
        injected = self._hrp_transport is not None
        hrp = self._hrp_transport if self._hrp_transport is not None else _construct_hrp_transport()
        adapter = self._setup_hrp(hrp, resolved_url, params)
        if not injected and not hrp.connect():
            raise ConnectionFailedError(hrp.getLastMessage())

        try:
            return self._run_hrp_transcribe(
                hrp,
                adapter,
                audio,
                raise_on_error=raise_on_error,
                receive_timeout=params.receive_timeout,
            )
        finally:
            if not injected:
                # 実 transport は disconnect で後始末する
                with suppress(Exception):
                    hrp.disconnect()

    def _setup_hrp(self, hrp: HrpTransport, api_url: str, params: RecognitionParams) -> _HrpListenerAdapter:
        """HRP トランスポートに接続パラメータを設定し、結果を受け取るアダプターを返す。"""
        adapter = _HrpListenerAdapter()
        hrp.setListener(adapter)

        hrp.setServerURL(api_url)
        hrp.setServiceAuthorization(self._api_key)

        keep_filler = None if params.keep_filler_token is None else bool_string(params.keep_filler_token)
        interval = None if params.result_updated_interval is None else str(params.result_updated_interval)
        recognition_timeout = None if params.recognition_timeout is None else str(params.recognition_timeout)
        confidence_level = None if params.confidence_level is None else repr(params.confidence_level)
        extension = resolve_billing_extension(params.extension, params.billing_key)
        optional_setters: "tuple[tuple[Callable[[str | None], None], str | None], ...]" = (
            (hrp.setGrammarFileNames, params.grammar_file_names),
            (hrp.setCodec, params.codec),
            (hrp.setResultType, params.result_type),
            (hrp.setProxyServerName, params.proxy_server_name),
            (hrp.setResultEncoding, params.result_encoding),
            (hrp.setVoiceDetection, params.voice_detection),
            (hrp.setAcceptTopic, params.accept_topic),
            (hrp.setContentType, params.content_type),
            (hrp.setAccept, params.accept),
            (hrp.setDomainId, params.domain_id),
            (hrp.setConfidenceLevel, confidence_level),
            (hrp.setMode, params.mode),
            (hrp.setProfileId, params.profile_id),
            (hrp.setProfileWords, params.profile_words),
            (hrp.setSegmenterType, params.segmenter_type),
            (hrp.setSegmenterProperties, params.segmenter_properties),
            (hrp.setExtension, extension),
            (hrp.setKeepFillerToken, keep_filler),
            (hrp.setResultUpdatedInterval, interval),
            (hrp.setRecognitionTimeout, recognition_timeout),
        )
        for setter, value in optional_setters:
            if value is not None:
                setter(value)

        if params.connect_timeout > 0:
            hrp.setConnectTimeout(params.connect_timeout)
        if params.receive_timeout > 0:
            hrp.setReceiveTimeout(params.receive_timeout)

        return adapter

    def _run_hrp_transcribe(
        self,
        hrp: HrpTransport,
        adapter: _HrpListenerAdapter,
        audio: AudioSource,
        *,
        raise_on_error: bool,
        receive_timeout: int,
    ) -> RecognitionResult:
        """HRP トランスポートに音声を送信し認識結果を返す。"""
        audio_bytes = resolve_audio(audio)

        if not hrp.feedDataResume():
            raise RecognitionError(hrp.getLastMessage())

        for offset in range(0, len(audio_bytes), 4096):
            chunk = audio_bytes[offset : offset + 4096]
            if not hrp.feedData(chunk, 0, len(chunk)):
                raise RecognitionError(hrp.getLastMessage())

        if not hrp.feedDataPause():
            raise RecognitionError(hrp.getLastMessage())

        timeout_sec = (receive_timeout / 1000.0) if receive_timeout > 0 else None
        completed = adapter.finalized_event.wait(timeout=timeout_sec)
        if not completed:
            raise RecognitionError("Timed out waiting for recognition result")
        if adapter.raw_result is None:
            raise RecognitionError("No recognition result was finalized")
        result = parse_result(adapter.raw_result, raise_on_error=raise_on_error)
        if adapter.session_id is not None:
            result = replace(result, session_id=adapter.session_id)
        return result

    # ------------------------------------------------------------------
    # WRP: stream()
    # ------------------------------------------------------------------

    def stream(  # noqa: PLR0913
        self,
        *,
        grammar_file_names: str | None | _UnsetType = UNSET,
        codec: str | None | _UnsetType = UNSET,
        result_type: str | None | _UnsetType = UNSET,
        proxy_server_name: str | None | _UnsetType = UNSET,
        connect_timeout: int | _UnsetType = UNSET,
        receive_timeout: int | _UnsetType = UNSET,
        mode: str | None | _UnsetType = UNSET,
        profile_id: str | None | _UnsetType = UNSET,
        profile_words: str | None | _UnsetType = UNSET,
        segmenter_type: str | None | _UnsetType = UNSET,
        segmenter: SegmenterProperties | None | _UnsetType = UNSET,
        segmenter_properties: str | None | _UnsetType = UNSET,
        confidence_level: float | None | _UnsetType = UNSET,
        keep_filler_token: bool | None | _UnsetType = UNSET,
        result_updated_interval: int | None | _UnsetType = UNSET,
        extension: str | None | _UnsetType = UNSET,
        billing_key: str | None | _UnsetType = UNSET,
        recognition_timeout: int | None | _UnsetType = UNSET,
        no_input_timeout: int | None | _UnsetType = UNSET,
        api_url: str | _UnsetType = UNSET,
    ) -> StreamConnectionManager:
        """WebSocket ストリーミング認識セッションのコンテキストマネージャを返す。

        ``with client.stream() as session:`` ブロック内で WS 接続が確立される。
        呼び出し時に指定した設定は、その呼び出しに限ってコンストラクタ時の設定を上書きする。
        引数を省略した場合はインスタンスに保持された同名設定を使用する。

        Args:
            grammar_file_names: 接続エンジン名の呼び出し時 override。
            codec: 音声コーデックの呼び出し時 override。
            result_type: 認識結果タイプの呼び出し時 override。
            proxy_server_name: プロキシサーバ名の呼び出し時 override。
            connect_timeout: 接続タイムアウト（ミリ秒）の呼び出し時 override。
            receive_timeout: 受信タイムアウト（ミリ秒）の呼び出し時 override。
            mode: 認識モードの呼び出し時 override。
            profile_id: プロファイル ID の呼び出し時 override。
            profile_words: セッション単語登録リストの呼び出し時 override。
            segmenter_type: セグメンタータイプの呼び出し時 override。
            segmenter: 型付きセグメンター設定の呼び出し時 override。
            segmenter_properties: セグメンター設定の呼び出し時 override。
            keep_filler_token: フィラー単語出力設定の呼び出し時 override。
            result_updated_interval: 途中結果発行間隔の呼び出し時 override。
            extension: 使用量集計タグの呼び出し時 override。
            billing_key: 使用量集計タグの呼び出し時 override。
            recognition_timeout: 認識タイムアウト（ミリ秒）の呼び出し時 override。
            confidence_level: 発話区間の信頼度しきい値（0.0 以上 1.0 以下）の呼び出し時 override。
            no_input_timeout: 無入力タイムアウトの呼び出し時 override。
            api_url: WRP API エンドポイント URL の呼び出し時 override。

        Returns:
            ``StreamConnectionManager``。``__enter__`` で ``StreamSession`` を返す。

        Raises:
            ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
                ``extension`` と ``billing_key`` を同時指定した場合。

        Example::

            with (
                client.stream() as session
            ):
                session.write(
                    audio_chunk
                )
                for event in session.poll():
                    if event.is_final:
                        print(
                            event.text
                        )
                session.end()
        """
        resolved_segmenter_properties = _resolve_segmenter_override(segmenter, segmenter_properties)
        params = merge_params(
            self._params,
            grammar_file_names=grammar_file_names,
            codec=codec,
            result_type=result_type,
            proxy_server_name=proxy_server_name,
            connect_timeout=connect_timeout,
            receive_timeout=receive_timeout,
            mode=mode,
            profile_id=profile_id,
            profile_words=profile_words,
            segmenter_type=segmenter_type,
            segmenter_properties=resolved_segmenter_properties,
            confidence_level=confidence_level,
            keep_filler_token=keep_filler_token,
            result_updated_interval=result_updated_interval,
            extension=extension,
            billing_key=billing_key,
            recognition_timeout=recognition_timeout,
            no_input_timeout=no_input_timeout,
        )
        resolved_url = _resolve_url(api_url, self._ws_api_url)
        return StreamConnectionManager(
            api_key=self._api_key,
            api_url=resolved_url,
            params=params,
            wrp_transport=self._wrp_transport,
        )


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def transcribe(  # noqa: PLR0913
    audio: AudioSource,
    *,
    api_key: str | None = None,
    api_url: str = _DEFAULT_HRP_URL,
    grammar_file_names: str | None = None,
    codec: str | None = None,
    result_type: str | None = None,
    proxy_server_name: str | None = None,
    connect_timeout: int = 0,
    receive_timeout: int = 0,
    mode: str | None = None,
    profile_id: str | None = None,
    profile_words: str | None = None,
    segmenter_type: str | None = None,
    segmenter: SegmenterProperties | None = None,
    segmenter_properties: str | None = None,
    confidence_level: float | None = None,
    keep_filler_token: bool | None = None,
    result_updated_interval: int | None = None,
    extension: str | None = None,
    billing_key: str | None = None,
    recognition_timeout: int | None = None,
    result_encoding: str | None = None,
    voice_detection: str | None = None,
    accept_topic: str | None = None,
    content_type: str | None = None,
    accept: str | None = None,
    domain_id: str | None = None,
    raise_on_error: bool = True,
    _transport: HrpTransport | None = None,
) -> RecognitionResult:
    """音声を AmiVoice HTTP API に送信し、認識結果を返す（モジュールレベル便利関数）。

    接続・切断はこの関数が内部で管理する。呼び出しごとに独立した接続を生成するためスレッドセーフ。
    多数の音声を処理する場合は ``AmiVoiceClient`` を生成して再利用する方が効率的。

    Args:
        audio: 音声ソース（bytes・バイナリストリーム・ファイルパス）。
        api_key: 認証情報。省略時は環境変数 ``AMIVOICE_API_KEY`` を使用する。
        api_url: AmiVoice API の接続先 URL。
        grammar_file_names: 接続エンジン名。
        codec: 音声コーデック（例: ``"16K"``, ``"8K"``）。
        result_type: 認識結果タイプ。
        proxy_server_name: プロキシサーバ名。
        connect_timeout: 接続タイムアウト（ミリ秒）。0 は無制限。
        receive_timeout: 受信タイムアウト（ミリ秒）。0 は無制限。
        mode: 認識モード。
        profile_id: プロファイル ID。
        profile_words: セッション単語登録リスト。
        segmenter_type: セグメンタータイプ。
        segmenter: 発話検出、話者ダイアライゼーション、言語識別の型付き設定。
        segmenter_properties: セグメンター設定。
        keep_filler_token: フィラー単語を出力するか。
        result_updated_interval: 途中結果の発行間隔（ミリ秒）。
        extension: 使用量集計タグ。
        billing_key: 使用量集計タグを専用形式で指定する文字列。
        recognition_timeout: 認識タイムアウト（ミリ秒）。0 は無制限。
        result_encoding: 認識結果の文字エンコーディング。
        voice_detection: 発話区間検出パラメータ。
        accept_topic: HTTP ``Accept-Topic`` ヘッダ。
        content_type: HTTP ``Content-Type`` ヘッダ。
        accept: HTTP ``Accept`` ヘッダ。
        domain_id: ドメイン ID。
        confidence_level: 発話区間の信頼度しきい値（0.0 以上 1.0 以下）。
        raise_on_error: エラー結果の場合に ``RecognitionError`` を送出するか否か。
        _transport: テスト用 HRP トランスポート注入口（非公開）。

    Returns:
        認識結果。

    Raises:
        AuthenticationError: ``api_key`` が指定されず環境変数も設定されていない場合。
        ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
            ``extension`` と ``billing_key`` を同時指定した場合。
        ConnectionFailedError: AmiVoice API への接続に失敗した場合。
        RecognitionError: 音声認識処理中にエラーが発生した場合。
    """
    client = AmiVoiceClient(
        api_key=api_key,
        grammar_file_names=grammar_file_names,
        codec=codec,
        result_type=result_type,
        proxy_server_name=proxy_server_name,
        connect_timeout=connect_timeout,
        receive_timeout=receive_timeout,
        mode=mode,
        profile_id=profile_id,
        profile_words=profile_words,
        segmenter_type=segmenter_type,
        segmenter=segmenter,
        segmenter_properties=segmenter_properties,
        keep_filler_token=keep_filler_token,
        result_updated_interval=result_updated_interval,
        extension=extension,
        billing_key=billing_key,
        recognition_timeout=recognition_timeout,
        result_encoding=result_encoding,
        voice_detection=voice_detection,
        accept_topic=accept_topic,
        content_type=content_type,
        accept=accept,
        domain_id=domain_id,
        confidence_level=confidence_level,
        hrp_transport=_transport,
    )
    return client.transcribe(audio, raise_on_error=raise_on_error, api_url=api_url)
