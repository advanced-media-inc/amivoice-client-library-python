"""AmiVoice 高レベルクライアント。HTTP 認識 (transcribe) と WebSocket ストリーミング (stream) を提供する。"""

import os
import threading
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import replace
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable

from com.amivoice.hrp.Hrp import Hrp as _Hrp
from com.amivoice.hrp.HrpListener import HrpListener

from ._audio import resolve_audio
from ._billing import resolve_billing_extension
from ._params import UNSET, RecognitionParams, _UnsetType, merge_params
from ._segmenter import SegmenterProperties
from ._stream import StreamConnectionManager
from ._transport import HrpTransport, WrpTransport, _set_optional_transport_parameter, bool_string
from ._types import AudioSource
from .dictionary import ProfileWord, build_profile_words
from .exceptions import AuthenticationError, ConfigurationError, ConnectionFailedError, RecognitionError
from .models import RecognitionResult, parse_result

_DEFAULT_HRP_URL: str = "https://acp-api.amivoice.com/v1/recognize"
_DEFAULT_WRP_URL: str = "wss://acp-api.amivoice.com/v1/"
_DEFAULT_NOLOG_HRP_URL: str = "https://acp-api.amivoice.com/v1/nolog/recognize"
_DEFAULT_NOLOG_WRP_URL: str = "wss://acp-api.amivoice.com/v1/nolog/"


def _construct_hrp_transport() -> HrpTransport:
    """HRP ライブラリのトランスポートを生成する。

    Returns:
        HrpTransport: 生成した HRP トランスポート
    """
    return _Hrp.construct()


def _validate_custom_url_logging_opt_out(url: str, nolog_url: str) -> None:
    """``logging_opt_out`` が有効なときにカスタム URL がログ保存なしのパスか検証する

    カスタム URL はホスト名を保ったまま使うため、PrivateLink などのホスト名は許容し、
    パスだけをログ保存なしのエンドポイントと比較する

    Args:
        url (str): 検証するカスタム URL
        nolog_url (str): 比較対象のログ保存なしの既定エンドポイント URL

    Raises:
        ConfigurationError: カスタム URL のパスがログ保存なしのエンドポイントと一致しない場合
    """
    nolog_path = urlsplit(nolog_url).path
    if not isinstance(url, str) or urlsplit(url).path != nolog_path:
        raise ConfigurationError(f"Custom URL must use the '{nolog_path}' path when logging_opt_out is True")


def _validate_logging_opt_out(logging_opt_out: object) -> bool:
    """``logging_opt_out`` が bool であることを検証する

    ``None`` や文字列を False または True として解釈すると、意図せずログが保存されるため拒否する

    Args:
        logging_opt_out (object): 検証する ``logging_opt_out`` の値

    Returns:
        bool: 検証済みの ``logging_opt_out``

    Raises:
        ConfigurationError: ``logging_opt_out`` が bool でない場合
    """
    if not isinstance(logging_opt_out, bool):
        raise ConfigurationError("Invalid logging_opt_out: must be a boolean")
    return logging_opt_out


def _resolve_logging_opt_out(override: bool | _UnsetType, configured: bool) -> bool:
    """呼び出し時の ``logging_opt_out`` override とコンストラクタ設定から最終値を解決する

    Args:
        override (bool | _UnsetType): 呼び出し時の override。``UNSET`` は未指定を表す
        configured (bool): コンストラクタで設定された値

    Returns:
        bool: 解決した ``logging_opt_out``

    Raises:
        ConfigurationError: override が bool でも ``UNSET`` でもない場合
    """
    if isinstance(override, _UnsetType):
        return configured
    return _validate_logging_opt_out(override)


def _resolve_endpoint_url(
    override: str | _UnsetType,
    configured_url: str,
    configured_url_is_default: bool,
    nolog_url: str,
    logging_opt_out: bool,
) -> str:
    """URL override とログ保存なし設定から最終エンドポイントを解決する。

    既定 URL だけを nolog エンドポイントへ切り替える。カスタム URL は書き換えず、
    ``logging_opt_out`` が有効な場合はログ保存なしのパスであることを検証する。

    Args:
        override (str | _UnsetType): 呼び出し時の URL override。``UNSET`` は未指定を表す
        configured_url (str): コンストラクタで設定された URL
        configured_url_is_default (bool): コンストラクタで URL を省略したかどうか。
            明示的に既定 URL と同じ値を指定した場合との区別に使用する
        nolog_url (str): ログ保存なしの既定エンドポイント URL
        logging_opt_out (bool): ログ保存なしのエンドポイントを使用するかどうか

    Returns:
        str: 解決されたエンドポイント URL

    Raises:
        ConfigurationError: ``logging_opt_out`` が有効でカスタム URL がログ保存なしのパスでない場合
    """
    if isinstance(override, _UnsetType) and configured_url_is_default:
        return nolog_url if logging_opt_out else configured_url
    url = configured_url if isinstance(override, _UnsetType) else override
    if logging_opt_out:
        _validate_custom_url_logging_opt_out(url, nolog_url)
    return url


def _resolve_profile_words(profile_words: str | Sequence[ProfileWord] | None) -> str | None:
    """ProfileWord シーケンスまたは既存の文字列を profileWords 文字列へ解決する

    空の ProfileWord シーケンスは ``setProfileWords("")`` で空のパラメータを送らないよう None として扱う

    Args:
        profile_words (str | Sequence[ProfileWord] | None): 既存の wire format 文字列またはシリアライズする ProfileWord シーケンス

    Returns:
        str | None: トランスポートへ渡す profileWords 文字列、空のシーケンスの場合は None
    """
    if profile_words is None or isinstance(profile_words, str):
        return profile_words
    if len(profile_words) == 0:
        return None
    return build_profile_words(profile_words)


def _resolve_profile_words_override(
    profile_words: str | Sequence[ProfileWord] | None | _UnsetType,
) -> str | None | _UnsetType:
    """呼び出し時 profile_words override を解決し、未指定 sentinel を保持する。

    Args:
        profile_words (str | Sequence[ProfileWord] | None | _UnsetType): 呼び出し時の profile_words override

    Returns:
        str | None | _UnsetType: 解決した profileWords 文字列、``None``、または未指定 sentinel
    """
    if isinstance(profile_words, _UnsetType):
        return profile_words
    return _resolve_profile_words(profile_words)


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
        profile_words: ワイヤー形式文字列または ``ProfileWord`` シーケンスのセッション単語登録リスト。
        segmenter_type: セグメンタータイプ。
        segmenter: 発話検出、話者ダイアライゼーション、言語識別の型付き設定。
        segmenter_properties: セグメンター設定。
        keep_filler_token: フィラー単語を出力するか。
        result_updated_interval: 途中結果の発行間隔（ミリ秒）。
        extension: 使用量集計タグ。
        billing_key: 使用量集計タグを専用形式で指定する文字列。
        recognition_timeout: 認識タイムアウト（ミリ秒）。0 は無制限。
        max_decoding_time: 認識処理時間の上限（ミリ秒）、0 は無効
        max_response_time: 音声時間に加える応答時間の上限（ミリ秒）、リアルタイム録音時のみ有効、0 は無効
        max_decoding_rate: 音声時間に対する認識処理時間倍率の上限、バッチ音声のみ有効、負値は無効
        target_response_time: 暫定結果の目標応答時間（ミリ秒）、リアルタイム録音時のみ有効、0 は無効
        target_decoding_rate: 暫定結果の目標認識処理時間倍率、バッチ音声のみ有効、負値は無効
        result_encoding: 認識結果の文字エンコーディング（HRP 専用）。
        voice_detection: 発話区間検出パラメータ。
        accept_topic: HTTP ``Accept-Topic`` ヘッダ（HRP 専用）。
        content_type: HTTP ``Content-Type`` ヘッダ（HRP 専用）。
        accept: HTTP ``Accept`` ヘッダ（HRP 専用）。
        domain_id: ドメイン ID（HRP 専用）。
        confidence_level: 発話区間の信頼度しきい値（0.0 以上 1.0 以下）。
        no_input_timeout: 無入力タイムアウト（ミリ秒）（WRP 専用）。
        complete_timeout: ルールグラマの確定待ちタイムアウト（ミリ秒） 0 以上
        wildcard_model_penalty: ルールグラマのワイルドカードモデルペナルティ 負値は無効
        logging_opt_out: ログを保存しないエンドポイントを使用するか。
            カスタムURLは書き換えず、ログ保存なしのパスでなければエラーにする。
        http_api_url: HRP（HTTP）API エンドポイント URL の既定値。
        ws_api_url: WRP（WebSocket）API エンドポイント URL の既定値。
        hrp_transport: テスト用 HRP トランスポート注入口。
        wrp_transport: テスト用 WRP トランスポート注入口。

    Raises:
        AuthenticationError: ``api_key`` が指定されず環境変数も設定されていない場合。
        ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
            ``extension`` と ``billing_key`` を同時指定した場合。
            ``logging_opt_out`` が有効でカスタム URL がログ保存なしのパスでない場合。
            ``logging_opt_out`` が bool でない場合。

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
        profile_words: str | Sequence[ProfileWord] | None = None,
        logging_opt_out: bool = False,
        segmenter_type: str | None = None,
        segmenter: SegmenterProperties | None = None,
        segmenter_properties: str | None = None,
        confidence_level: float | None = None,
        keep_filler_token: bool | None = None,
        result_updated_interval: int | None = None,
        extension: str | None = None,
        billing_key: str | None = None,
        recognition_timeout: int | None = None,
        complete_timeout: int | None = None,
        wildcard_model_penalty: float | None = None,
        max_decoding_time: int | None = None,
        max_response_time: int | None = None,
        max_decoding_rate: float | None = None,
        target_response_time: int | None = None,
        target_decoding_rate: float | None = None,
        result_encoding: str | None = None,
        voice_detection: str | None = None,
        accept_topic: str | None = None,
        content_type: str | None = None,
        accept: str | None = None,
        domain_id: str | None = None,
        no_input_timeout: int | None = None,
        http_api_url: str | _UnsetType = UNSET,
        ws_api_url: str | _UnsetType = UNSET,
        hrp_transport: HrpTransport | None = None,
        wrp_transport: WrpTransport | None = None,
    ) -> None:
        """クライアント設定を保持し、未指定時は環境変数から API キーを解決する。

        Args:
            api_key (str | None): 認証情報。省略時は環境変数 ``AMIVOICE_API_KEY`` を使用する
            grammar_file_names (str | None): 接続エンジン名
            codec (str | None): 音声コーデック
            result_type (str | None): 認識結果タイプ
            proxy_server_name (str | None): プロキシサーバ名
            connect_timeout (int): 接続タイムアウト（ミリ秒）。0 は無制限
            receive_timeout (int): 受信タイムアウト（ミリ秒）。0 は無制限
            mode (str | None): 認識モード
            profile_id (str | None): プロファイル ID
            profile_words (str | Sequence[ProfileWord] | None): セッション単語登録リスト
            logging_opt_out (bool): ログを保存しないエンドポイントを使用するか。カスタム URL は書き換えず、
                ログ保存なしのパスでなければエラーにする
            segmenter_type (str | None): セグメンタータイプ
            segmenter (SegmenterProperties | None): 型付きセグメンター設定
            segmenter_properties (str | None): セグメンター設定
            confidence_level (float | None): 発話区間の信頼度しきい値
            keep_filler_token (bool | None): フィラー単語を出力するか
            result_updated_interval (int | None): 途中結果の発行間隔（ミリ秒）
            extension (str | None): 使用量集計タグ
            billing_key (str | None): 使用量集計タグを専用形式で指定する文字列
            recognition_timeout (int | None): 認識タイムアウト（ミリ秒）
            complete_timeout (int | None): ルールグラマの確定待ちタイムアウト（ミリ秒）
            wildcard_model_penalty (float | None): ルールグラマのワイルドカードモデルペナルティ
            max_decoding_time (int | None): 認識処理時間の上限（ミリ秒）
            max_response_time (int | None): 音声時間に加える応答時間の上限（ミリ秒）
            max_decoding_rate (float | None): 音声時間に対する認識処理時間倍率の上限
            target_response_time (int | None): 暫定結果の目標応答時間（ミリ秒）
            target_decoding_rate (float | None): 暫定結果の目標認識処理時間倍率
            result_encoding (str | None): 認識結果の文字エンコーディング（HRP 専用）
            voice_detection (str | None): 発話区間検出パラメータ
            accept_topic (str | None): HTTP ``Accept-Topic`` ヘッダ（HRP 専用）
            content_type (str | None): HTTP ``Content-Type`` ヘッダ（HRP 専用）
            accept (str | None): HTTP ``Accept`` ヘッダ（HRP 専用）
            domain_id (str | None): ドメイン ID（HRP 専用）
            no_input_timeout (int | None): 無入力タイムアウト（ミリ秒）（WRP 専用）
            http_api_url (str | _UnsetType): HRP API エンドポイント URL。``UNSET`` は既定 URL を使用する
            ws_api_url (str | _UnsetType): WRP API エンドポイント URL。``UNSET`` は既定 URL を使用する
            hrp_transport (HrpTransport | None): テスト用 HRP トランスポート注入口
            wrp_transport (WrpTransport | None): テスト用 WRP トランスポート注入口

        Raises:
            AuthenticationError: ``api_key`` が指定されず環境変数も設定されていない場合
            ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
                ``extension`` と ``billing_key`` を同時指定した場合、``logging_opt_out`` が bool でない場合、
                または ``logging_opt_out`` が有効でカスタム URL がログ保存なしのパスでない場合
        """
        resolved_key = api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY")
        if resolved_key is None:
            raise AuthenticationError("AMIVOICE_API_KEY is not set")

        resolved_segmenter_properties = _resolve_segmenter_properties(segmenter, segmenter_properties)
        resolved_profile_words = _resolve_profile_words(profile_words)
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
            profile_words=resolved_profile_words,
            segmenter_type=segmenter_type,
            segmenter_properties=resolved_segmenter_properties,
            keep_filler_token=keep_filler_token,
            result_updated_interval=result_updated_interval,
            extension=extension,
            billing_key=billing_key,
            recognition_timeout=recognition_timeout,
            complete_timeout=complete_timeout,
            wildcard_model_penalty=wildcard_model_penalty,
            result_encoding=result_encoding,
            voice_detection=voice_detection,
            accept_topic=accept_topic,
            content_type=content_type,
            accept=accept,
            domain_id=domain_id,
            confidence_level=confidence_level,
            max_decoding_time=max_decoding_time,
            max_response_time=max_response_time,
            max_decoding_rate=max_decoding_rate,
            target_response_time=target_response_time,
            target_decoding_rate=target_decoding_rate,
            no_input_timeout=no_input_timeout,
        )
        self._http_api_url = _DEFAULT_HRP_URL if isinstance(http_api_url, _UnsetType) else http_api_url
        self._ws_api_url = _DEFAULT_WRP_URL if isinstance(ws_api_url, _UnsetType) else ws_api_url
        self._http_api_url_is_default = isinstance(http_api_url, _UnsetType)
        self._ws_api_url_is_default = isinstance(ws_api_url, _UnsetType)
        self._logging_opt_out = _validate_logging_opt_out(logging_opt_out)
        if self._logging_opt_out:
            if not self._http_api_url_is_default:
                _validate_custom_url_logging_opt_out(self._http_api_url, _DEFAULT_NOLOG_HRP_URL)
            if not self._ws_api_url_is_default:
                _validate_custom_url_logging_opt_out(self._ws_api_url, _DEFAULT_NOLOG_WRP_URL)
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
        profile_words: str | Sequence[ProfileWord] | None | _UnsetType = UNSET,
        segmenter_type: str | None | _UnsetType = UNSET,
        segmenter: SegmenterProperties | None | _UnsetType = UNSET,
        segmenter_properties: str | None | _UnsetType = UNSET,
        confidence_level: float | None | _UnsetType = UNSET,
        keep_filler_token: bool | None | _UnsetType = UNSET,
        result_updated_interval: int | None | _UnsetType = UNSET,
        extension: str | None | _UnsetType = UNSET,
        billing_key: str | None | _UnsetType = UNSET,
        recognition_timeout: int | None | _UnsetType = UNSET,
        complete_timeout: int | None | _UnsetType = UNSET,
        wildcard_model_penalty: float | None | _UnsetType = UNSET,
        max_decoding_time: int | None | _UnsetType = UNSET,
        max_response_time: int | None | _UnsetType = UNSET,
        max_decoding_rate: float | None | _UnsetType = UNSET,
        target_response_time: int | None | _UnsetType = UNSET,
        target_decoding_rate: float | None | _UnsetType = UNSET,
        result_encoding: str | None | _UnsetType = UNSET,
        voice_detection: str | None | _UnsetType = UNSET,
        accept_topic: str | None | _UnsetType = UNSET,
        content_type: str | None | _UnsetType = UNSET,
        accept: str | None | _UnsetType = UNSET,
        domain_id: str | None | _UnsetType = UNSET,
        raise_on_error: bool = True,
        api_url: str | _UnsetType = UNSET,
        logging_opt_out: bool | _UnsetType = UNSET,
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
            profile_words: ワイヤー形式文字列または ``ProfileWord`` シーケンスの呼び出し時 override。
            segmenter_type: セグメンタータイプの呼び出し時 override。
            segmenter: 型付きセグメンター設定の呼び出し時 override。
            segmenter_properties: セグメンター設定の呼び出し時 override。
            keep_filler_token: フィラー単語出力設定の呼び出し時 override。
            result_updated_interval: 途中結果発行間隔の呼び出し時 override。
            extension: 使用量集計タグの呼び出し時 override。
            billing_key: 使用量集計タグの呼び出し時 override。
            recognition_timeout: 認識タイムアウト（ミリ秒）の呼び出し時 override。
            complete_timeout: ルールグラマの確定待ちタイムアウト（ミリ秒）の呼び出し時 override 0 以上
            wildcard_model_penalty: ルールグラマのワイルドカードモデルペナルティの呼び出し時 override 負値は無効
            max_decoding_time: 認識処理時間の上限（ミリ秒）の呼び出し時 override、0 は無効
            max_response_time: 応答時間の上限（ミリ秒）の呼び出し時 override、リアルタイム録音時のみ有効、0 は無効
            max_decoding_rate: 認識処理時間倍率の上限の呼び出し時 override、バッチ音声のみ有効、負値は無効
            target_response_time: 目標応答時間（ミリ秒）の呼び出し時 override、リアルタイム録音時のみ有効、0 は無効
            target_decoding_rate: 目標認識処理時間倍率の呼び出し時 override、バッチ音声のみ有効、負値は無効
            result_encoding: 認識結果エンコーディングの呼び出し時 override。
            voice_detection: 発話区間検出パラメータの呼び出し時 override。
            accept_topic: HTTP ``Accept-Topic`` ヘッダの呼び出し時 override。
            content_type: HTTP ``Content-Type`` ヘッダの呼び出し時 override。
            accept: HTTP ``Accept`` ヘッダの呼び出し時 override。
            domain_id: ドメイン ID の呼び出し時 override。
            confidence_level: 発話区間の信頼度しきい値（0.0 以上 1.0 以下）の呼び出し時 override。
            raise_on_error: エラー結果の場合に ``RecognitionError`` を送出するか否か。
            api_url: HRP API エンドポイント URL の呼び出し時 override。指定時はカスタムURLとして扱う。
            logging_opt_out: 既定URLをログ保存なしエンドポイントへ切り替える呼び出し時 override。
                カスタムURLは書き換えず、ログ保存なしのパスでなければエラーにする。

        Returns:
            認識結果。

        Raises:
            ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
                ``extension`` と ``billing_key`` を同時指定した場合。
                ``logging_opt_out`` が有効でカスタム URL がログ保存なしのパスでない場合。
                ``logging_opt_out`` が bool でない場合。
            ConnectionFailedError: AmiVoice API への接続に失敗した場合。
            RecognitionError: 音声認識処理中にエラーが発生した場合。
        """
        resolved_segmenter_properties = _resolve_segmenter_override(segmenter, segmenter_properties)
        resolved_profile_words = _resolve_profile_words_override(profile_words)
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
            profile_words=resolved_profile_words,
            segmenter_type=segmenter_type,
            segmenter_properties=resolved_segmenter_properties,
            keep_filler_token=keep_filler_token,
            result_updated_interval=result_updated_interval,
            extension=extension,
            billing_key=billing_key,
            recognition_timeout=recognition_timeout,
            complete_timeout=complete_timeout,
            wildcard_model_penalty=wildcard_model_penalty,
            result_encoding=result_encoding,
            voice_detection=voice_detection,
            accept_topic=accept_topic,
            content_type=content_type,
            accept=accept,
            domain_id=domain_id,
            confidence_level=confidence_level,
            max_decoding_time=max_decoding_time,
            max_response_time=max_response_time,
            max_decoding_rate=max_decoding_rate,
            target_response_time=target_response_time,
            target_decoding_rate=target_decoding_rate,
        )
        resolved_logging_opt_out = _resolve_logging_opt_out(logging_opt_out, self._logging_opt_out)
        resolved_url = _resolve_endpoint_url(
            api_url,
            self._http_api_url,
            self._http_api_url_is_default,
            _DEFAULT_NOLOG_HRP_URL,
            resolved_logging_opt_out,
        )

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
        """HRP トランスポートに接続パラメータを設定し、結果を受け取るアダプターを返す。

        Args:
            hrp (HrpTransport): パラメータを設定する HRP トランスポート
            api_url (str): 接続先の HRP API エンドポイント URL
            params (RecognitionParams): HRP に適用する認識パラメータ

        Returns:
            _HrpListenerAdapter: 認識結果を受け取るリスナーアダプター
        """
        adapter = _HrpListenerAdapter()
        hrp.setListener(adapter)

        hrp.setServerURL(api_url)
        hrp.setServiceAuthorization(self._api_key)

        keep_filler = None if params.keep_filler_token is None else bool_string(params.keep_filler_token)
        interval = None if params.result_updated_interval is None else str(params.result_updated_interval)
        recognition_timeout = None if params.recognition_timeout is None else str(params.recognition_timeout)
        max_decoding_time = None if params.max_decoding_time is None else str(params.max_decoding_time)
        max_response_time = None if params.max_response_time is None else str(params.max_response_time)
        max_decoding_rate = None if params.max_decoding_rate is None else repr(params.max_decoding_rate)
        target_response_time = None if params.target_response_time is None else str(params.target_response_time)
        target_decoding_rate = None if params.target_decoding_rate is None else repr(params.target_decoding_rate)
        confidence_level = None if params.confidence_level is None else repr(params.confidence_level)
        extension = resolve_billing_extension(params.extension, params.billing_key)
        complete_timeout = None if params.complete_timeout is None else str(params.complete_timeout)
        wildcard_model_penalty = None if params.wildcard_model_penalty is None else repr(params.wildcard_model_penalty)
        _set_optional_transport_parameter(hrp, "setCompleteTimeout", complete_timeout)
        _set_optional_transport_parameter(hrp, "setWildcardModelPenalty", wildcard_model_penalty)
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
            (hrp.setMaxDecodingTime, max_decoding_time),
            (hrp.setMaxResponseTime, max_response_time),
            (hrp.setMaxDecodingRate, max_decoding_rate),
            (hrp.setTargetResponseTime, target_response_time),
            (hrp.setTargetDecodingRate, target_decoding_rate),
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
        """HRP トランスポートに音声を送信し認識結果を返す。

        Args:
            hrp (HrpTransport): 音声を送信する HRP トランスポート
            adapter (_HrpListenerAdapter): 認識結果を受け取るリスナーアダプター
            audio (AudioSource): 送信する音声ソース
            raise_on_error (bool): エラー結果で ``RecognitionError`` を送出するかどうか
            receive_timeout (int): 認識結果を待機するタイムアウト（ミリ秒）。0 は無制限

        Returns:
            RecognitionResult: 解析された認識結果

        Raises:
            RecognitionError: 音声送信または認識結果の取得に失敗した場合
        """
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
        profile_words: str | Sequence[ProfileWord] | None | _UnsetType = UNSET,
        segmenter_type: str | None | _UnsetType = UNSET,
        segmenter: SegmenterProperties | None | _UnsetType = UNSET,
        segmenter_properties: str | None | _UnsetType = UNSET,
        confidence_level: float | None | _UnsetType = UNSET,
        keep_filler_token: bool | None | _UnsetType = UNSET,
        result_updated_interval: int | None | _UnsetType = UNSET,
        extension: str | None | _UnsetType = UNSET,
        billing_key: str | None | _UnsetType = UNSET,
        recognition_timeout: int | None | _UnsetType = UNSET,
        complete_timeout: int | None | _UnsetType = UNSET,
        wildcard_model_penalty: float | None | _UnsetType = UNSET,
        max_decoding_time: int | None | _UnsetType = UNSET,
        max_response_time: int | None | _UnsetType = UNSET,
        max_decoding_rate: float | None | _UnsetType = UNSET,
        target_response_time: int | None | _UnsetType = UNSET,
        target_decoding_rate: float | None | _UnsetType = UNSET,
        no_input_timeout: int | None | _UnsetType = UNSET,
        api_url: str | _UnsetType = UNSET,
        logging_opt_out: bool | _UnsetType = UNSET,
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
            profile_words: ワイヤー形式文字列または ``ProfileWord`` シーケンスの呼び出し時 override。
            segmenter_type: セグメンタータイプの呼び出し時 override。
            segmenter: 型付きセグメンター設定の呼び出し時 override。
            segmenter_properties: セグメンター設定の呼び出し時 override。
            keep_filler_token: フィラー単語出力設定の呼び出し時 override。
            result_updated_interval: 途中結果発行間隔の呼び出し時 override。
            extension: 使用量集計タグの呼び出し時 override。
            billing_key: 使用量集計タグの呼び出し時 override。
            recognition_timeout: 認識タイムアウト（ミリ秒）の呼び出し時 override。
            complete_timeout: ルールグラマの確定待ちタイムアウト（ミリ秒）の呼び出し時 override 0 以上
            wildcard_model_penalty: ルールグラマのワイルドカードモデルペナルティの呼び出し時 override 負値は無効
            max_decoding_time: 認識処理時間の上限（ミリ秒）の呼び出し時 override、0 は無効
            max_response_time: 応答時間の上限（ミリ秒）の呼び出し時 override、リアルタイム録音時のみ有効、0 は無効
            max_decoding_rate: 認識処理時間倍率の上限の呼び出し時 override、バッチ音声のみ有効、負値は無効
            target_response_time: 目標応答時間（ミリ秒）の呼び出し時 override、リアルタイム録音時のみ有効、0 は無効
            target_decoding_rate: 目標認識処理時間倍率の呼び出し時 override、バッチ音声のみ有効、負値は無効
            confidence_level: 発話区間の信頼度しきい値（0.0 以上 1.0 以下）の呼び出し時 override。
            no_input_timeout: 無入力タイムアウトの呼び出し時 override。
            api_url: WRP API エンドポイント URL の呼び出し時 override。指定時はカスタムURLとして扱う。
            logging_opt_out: 既定URLをログ保存なしエンドポイントへ切り替える呼び出し時 override。
                カスタムURLは書き換えず、ログ保存なしのパスでなければエラーにする。

        Returns:
            ``StreamConnectionManager``。``__enter__`` で ``StreamSession`` を返す。

        Raises:
            ConfigurationError: ``segmenter`` と ``segmenter_properties``、または
                ``extension`` と ``billing_key`` を同時指定した場合。
                ``logging_opt_out`` が有効でカスタム URL がログ保存なしのパスでない場合。
                ``logging_opt_out`` が bool でない場合。

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
        resolved_profile_words = _resolve_profile_words_override(profile_words)
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
            profile_words=resolved_profile_words,
            segmenter_type=segmenter_type,
            segmenter_properties=resolved_segmenter_properties,
            confidence_level=confidence_level,
            max_decoding_time=max_decoding_time,
            max_response_time=max_response_time,
            max_decoding_rate=max_decoding_rate,
            target_response_time=target_response_time,
            target_decoding_rate=target_decoding_rate,
            keep_filler_token=keep_filler_token,
            result_updated_interval=result_updated_interval,
            extension=extension,
            billing_key=billing_key,
            recognition_timeout=recognition_timeout,
            complete_timeout=complete_timeout,
            wildcard_model_penalty=wildcard_model_penalty,
            no_input_timeout=no_input_timeout,
        )
        resolved_logging_opt_out = _resolve_logging_opt_out(logging_opt_out, self._logging_opt_out)
        resolved_url = _resolve_endpoint_url(
            api_url,
            self._ws_api_url,
            self._ws_api_url_is_default,
            _DEFAULT_NOLOG_WRP_URL,
            resolved_logging_opt_out,
        )
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
    api_url: str | _UnsetType = UNSET,
    logging_opt_out: bool = False,
    grammar_file_names: str | None = None,
    codec: str | None = None,
    result_type: str | None = None,
    proxy_server_name: str | None = None,
    connect_timeout: int = 0,
    receive_timeout: int = 0,
    mode: str | None = None,
    profile_id: str | None = None,
    profile_words: str | Sequence[ProfileWord] | None = None,
    segmenter_type: str | None = None,
    segmenter: SegmenterProperties | None = None,
    segmenter_properties: str | None = None,
    confidence_level: float | None = None,
    keep_filler_token: bool | None = None,
    result_updated_interval: int | None = None,
    extension: str | None = None,
    billing_key: str | None = None,
    recognition_timeout: int | None = None,
    complete_timeout: int | None = None,
    wildcard_model_penalty: float | None = None,
    max_decoding_time: int | None = None,
    max_response_time: int | None = None,
    max_decoding_rate: float | None = None,
    target_response_time: int | None = None,
    target_decoding_rate: float | None = None,
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
        api_url: AmiVoice API の接続先 URL。カスタムURLは ``logging_opt_out`` で書き換えない。
        logging_opt_out: ログを保存しない既定エンドポイントを使用するか。
        grammar_file_names: 接続エンジン名。
        codec: 音声コーデック（例: ``"16K"``, ``"8K"``）。
        result_type: 認識結果タイプ。
        proxy_server_name: プロキシサーバ名。
        connect_timeout: 接続タイムアウト（ミリ秒）。0 は無制限。
        receive_timeout: 受信タイムアウト（ミリ秒）。0 は無制限。
        mode: 認識モード。
        profile_id: プロファイル ID。
        profile_words: ワイヤー形式文字列または ``ProfileWord`` シーケンスのセッション単語登録リスト。
        segmenter_type: セグメンタータイプ。
        segmenter: 発話検出、話者ダイアライゼーション、言語識別の型付き設定。
        segmenter_properties: セグメンター設定。
        keep_filler_token: フィラー単語を出力するか。
        result_updated_interval: 途中結果の発行間隔（ミリ秒）。
        extension: 使用量集計タグ。
        billing_key: 使用量集計タグを専用形式で指定する文字列。
        recognition_timeout: 認識タイムアウト（ミリ秒）。0 は無制限。
        complete_timeout: ルールグラマの確定待ちタイムアウト（ミリ秒） 0 以上
        wildcard_model_penalty: ルールグラマのワイルドカードモデルペナルティ 負値は無効
        max_decoding_time: 認識処理時間の上限（ミリ秒）、0 は無効
        max_response_time: 音声時間に加える応答時間の上限（ミリ秒）、リアルタイム録音時のみ有効、0 は無効
        max_decoding_rate: 音声時間に対する認識処理時間倍率の上限、バッチ音声のみ有効、負値は無効
        target_response_time: 暫定結果の目標応答時間（ミリ秒）、リアルタイム録音時のみ有効、0 は無効
        target_decoding_rate: 暫定結果の目標認識処理時間倍率、バッチ音声のみ有効、負値は無効
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
            ``logging_opt_out`` が有効でカスタム URL がログ保存なしのパスでない場合。
            ``logging_opt_out`` が bool でない場合。
        ConnectionFailedError: AmiVoice API への接続に失敗した場合。
        RecognitionError: 音声認識処理中にエラーが発生した場合。
    """
    client = AmiVoiceClient(
        api_key=api_key,
        http_api_url=api_url,
        logging_opt_out=logging_opt_out,
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
        complete_timeout=complete_timeout,
        wildcard_model_penalty=wildcard_model_penalty,
        result_encoding=result_encoding,
        voice_detection=voice_detection,
        accept_topic=accept_topic,
        content_type=content_type,
        accept=accept,
        domain_id=domain_id,
        confidence_level=confidence_level,
        max_decoding_time=max_decoding_time,
        max_response_time=max_response_time,
        max_decoding_rate=max_decoding_rate,
        target_response_time=target_response_time,
        target_decoding_rate=target_decoding_rate,
        hrp_transport=_transport,
    )
    return client.transcribe(audio, raise_on_error=raise_on_error)
