"""AmiVoiceの非同期HTTP v2を通常の同期メソッドから利用する"""

import http.client
import ipaddress
import math
import os
import time
from collections.abc import Sequence
from urllib.parse import quote

from ._async_audio import AudioUpload, MultipartUpload, validate_async_options
from ._async_http_transport import AsyncHttpConnection, AsyncHttpTransport
from ._async_models import parse_job, parse_submission
from ._connection_settings import parse_http_proxy, parse_service_url
from ._http_api import validate_service_api_key
from ._params import UNSET, RecognitionParams, _UnsetType
from ._recognition_settings import resolve_recognition_overrides
from ._request_parameters import _request_values
from ._segmenter import SegmenterProperties
from ._types import AudioSource
from .async_models import AsyncJobSnapshot, AsyncJobSubmission
from .constants import Codec
from .dictionary import ProfileWord
from .exceptions import AsyncHttpApiError, AsyncJobError, AsyncJobTimeoutError, ConfigurationError, ConnectionFailedError

_DEFAULT_URL = "https://acp-api-async.amivoice.com/v2/recognitions"


def _endpoint(url: str) -> str:
    parsed = parse_service_url(url, ("https", "http"))
    if parsed.path.rstrip("/") != "/v2/recognitions":
        raise ConfigurationError("Async HTTP endpoint must use /v2/recognitions; v1 is not supported")
    if parsed.scheme == "http":
        try:
            local = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local = False
        if not local:
            raise ConfigurationError("Async HTTP requires HTTPS except for loopback test servers")
    return url.rstrip("/")


def _job_id(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in (".", "..")
        or any(ord(c) <= 32 or ord(c) == 127 or c in "/\\" for c in value)
    ):
        raise ConfigurationError("session_id must be a non-empty single path segment without control characters")
    return value


def _seconds(value: float, name: str) -> float:
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("Invalid seconds")
        return float(value)
    except (ValueError, OverflowError):
        raise ConfigurationError(name + " must be a finite positive number of seconds") from None


def _communication(params: RecognitionParams) -> None:
    for name in ("connect_timeout", "receive_timeout"):
        value = getattr(params, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ConfigurationError(name + " must be a non-negative integer in milliseconds")
    parse_http_proxy(params.proxy_server_name)


class AmiVoiceAsyncClient:
    """ジョブの登録・取得・完了待機、Pythonのasync/await APIではない"""

    def __init__(  # noqa: PLR0913
        self,
        api_key: str | None = None,
        *,
        grammar_file_names: str | None = None,
        codec: Codec | str | None = None,
        proxy_server_name: str | None = None,
        connect_timeout: int = 0,
        receive_timeout: int = 0,
        profile_id: str | None = None,
        profile_words: str | Sequence[ProfileWord] | None = None,
        segmenter: SegmenterProperties | None = None,
        segmenter_properties: str | None = None,
        selected_channel: int | tuple[int, int] | None = None,
        audio_filter_properties: str | None = None,
        confidence_level: float | None = None,
        keep_filler_token: bool | None = None,
        extension: str | None = None,
        billing_key: str | None = None,
        recognition_timeout: int | None = None,
        max_decoding_time: int | None = None,
        max_response_time: int | None = None,
        max_decoding_rate: float | None = None,
        target_response_time: int | None = None,
        target_decoding_rate: float | None = None,
        logging_opt_out: bool | None = None,
        content_id: str | None = None,
        compatible_with_sync: bool | None = None,
        api_url: str = _DEFAULT_URL,
        transport: AsyncHttpTransport | None = None,
    ) -> None:
        """認識設定と非同期HTTPの接続先を保持する

        Args:
            api_key (str | None): Bearer認証情報、省略時はAMIVOICE_API_KEY
            grammar_file_names (str | None): 作成時に必須の接続エンジン名、取得だけなら不要
            codec (Codec | str | None): 音声形式、ヘッダ付き音声では省略可
            proxy_server_name (str | None): HTTPプロキシ
            connect_timeout (int): 接続待機のミリ秒、0は無制限
            receive_timeout (int): ソケット送受信待機のミリ秒、0は無制限
            profile_id (str | None): 辞書参照ID
            profile_words (str | Sequence[ProfileWord] | None): セッション単語
            segmenter (SegmenterProperties | None): 発話検出と言語識別設定、同期話者設定は不可
            segmenter_properties (str | None): 発話検出と言語識別の設定文字列
            selected_channel (int | tuple[int, int] | None): 単一チャネル又は先頭からの平均範囲
            audio_filter_properties (str | None): チャネル指定の設定文字列
            confidence_level (float | None): 信頼度のしきい値
            keep_filler_token (bool | None): フィラーの保持、E2Eでは未指定にする
            extension (str | None): 使用量集計のJSON
            billing_key (str | None): 使用量集計タグ、extensionと排他
            recognition_timeout (int | None): サーバー側の認識完了制御、ミリ秒
            max_decoding_time (int | None): 最大認識処理時間、ミリ秒
            max_response_time (int | None): 最大応答時間、ミリ秒、バッチ音声では無効
            max_decoding_rate (float | None): 最大認識時間倍率
            target_response_time (int | None): 目標応答時間、ミリ秒、バッチ音声では無効
            target_decoding_rate (float | None): 目標認識時間倍率
            logging_opt_out (bool | None): 音声ログ保存なし、Noneはサーバー既定値
            content_id (str | None): ユーザー定義ID、冪等性キーではない
            compatible_with_sync (bool | None): 同期互換の結果形式
            api_url (str): v2エンドポイント、HTTPS又はローカルHTTP
            transport (AsyncHttpTransport | None): テスト用の通信処理
        """
        self._api_key = validate_service_api_key(api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY"))
        self._params = resolve_recognition_overrides(
            RecognitionParams(connect_timeout=connect_timeout, receive_timeout=receive_timeout),
            {name: value for name, value in locals().items() if value is not None},
        )
        _communication(self._params)
        if self._params.grammar_file_names is not None:
            _request_values(self._params, "async_http")
        validate_async_options(logging_opt_out, content_id, compatible_with_sync)
        self._logging_opt_out = logging_opt_out
        self._content_id = content_id
        self._compatible_with_sync = compatible_with_sync
        self._api_url = _endpoint(api_url)
        self._transport = transport if transport is not None else AsyncHttpConnection()
        self._clock = time.monotonic
        self._sleep = time.sleep

    def submit(  # noqa: PLR0913
        self,
        audio: AudioSource,
        *,
        grammar_file_names: str | None | _UnsetType = UNSET,
        codec: Codec | str | None | _UnsetType = UNSET,
        proxy_server_name: str | None | _UnsetType = UNSET,
        connect_timeout: int | _UnsetType = UNSET,
        receive_timeout: int | _UnsetType = UNSET,
        profile_id: str | None | _UnsetType = UNSET,
        profile_words: str | Sequence[ProfileWord] | None | _UnsetType = UNSET,
        segmenter: SegmenterProperties | None | _UnsetType = UNSET,
        segmenter_properties: str | None | _UnsetType = UNSET,
        selected_channel: int | tuple[int, int] | None | _UnsetType = UNSET,
        audio_filter_properties: str | None | _UnsetType = UNSET,
        confidence_level: float | None | _UnsetType = UNSET,
        keep_filler_token: bool | None | _UnsetType = UNSET,
        extension: str | None | _UnsetType = UNSET,
        billing_key: str | None | _UnsetType = UNSET,
        recognition_timeout: int | None | _UnsetType = UNSET,
        max_decoding_time: int | None | _UnsetType = UNSET,
        max_response_time: int | None | _UnsetType = UNSET,
        max_decoding_rate: float | None | _UnsetType = UNSET,
        target_response_time: int | None | _UnsetType = UNSET,
        target_decoding_rate: float | None | _UnsetType = UNSET,
        logging_opt_out: bool | None | _UnsetType = UNSET,
        content_id: str | None | _UnsetType = UNSET,
        compatible_with_sync: bool | None | _UnsetType = UNSET,
        api_url: str | _UnsetType = UNSET,
    ) -> AsyncJobSubmission:
        """音声を登録し、認識完了を待たず受付済みIDを返す

        未指定の引数はコンストラクタの設定を継承し、任意設定のNoneは送信を解除する
        通信失敗時に受理済みか分からないため、音声を自動再送しない

        Args:
            audio (AudioSource): bytes、Path、ファイルパス、バイナリストリーム
            grammar_file_names (str | None | _UnsetType): 今回のエンジン名
            codec (Codec | str | None | _UnsetType): 今回の音声形式
            proxy_server_name (str | None | _UnsetType): HTTPプロキシ
            connect_timeout (int | _UnsetType): 接続待機のミリ秒
            receive_timeout (int | _UnsetType): 送受信待機のミリ秒
            profile_id (str | None | _UnsetType): 辞書参照
            profile_words (str | Sequence[ProfileWord] | None | _UnsetType): セッション単語
            segmenter (SegmenterProperties | None | _UnsetType): 発話検出と言語識別
            segmenter_properties (str | None | _UnsetType): 設定文字列
            selected_channel (int | tuple[int, int] | None | _UnsetType): チャネル指定
            audio_filter_properties (str | None | _UnsetType): 音声フィルタの文字列
            confidence_level (float | None | _UnsetType): 信頼度しきい値
            keep_filler_token (bool | None | _UnsetType): フィラーの保持
            extension (str | None | _UnsetType): 集計設定JSON
            billing_key (str | None | _UnsetType): 集計タグ
            recognition_timeout (int | None | _UnsetType): サーバーの認識完了制御
            max_decoding_time (int | None | _UnsetType): 最大認識処理時間
            max_response_time (int | None | _UnsetType): 最大応答時間
            max_decoding_rate (float | None | _UnsetType): 最大倍率
            target_response_time (int | None | _UnsetType): 目標応答時間
            target_decoding_rate (float | None | _UnsetType): 目標倍率
            logging_opt_out (bool | None | _UnsetType): ログ保存設定
            content_id (str | None | _UnsetType): ユーザー定義ID
            compatible_with_sync (bool | None | _UnsetType): 同期互換結果
            api_url (str | _UnsetType): 今回だけ使用する接続先

        Returns:
            AsyncJobSubmission: 受付済みジョブID、元の応答

        Raises:
            ConfigurationError: 認識設定又は音声サイズが不正な場合
            AsyncHttpApiError: 受付失敗、HTTPエラー、不正応答
            ConnectionFailedError: 通信失敗、ジョブが受理された可能性がある
        """
        params = resolve_recognition_overrides(self._params, locals())
        _request_values(params, "async_http")
        _communication(params)
        url = self._url(api_url)
        options = (
            self._logging_opt_out if isinstance(logging_opt_out, _UnsetType) else logging_opt_out,
            self._content_id if isinstance(content_id, _UnsetType) else content_id,
            self._compatible_with_sync if isinstance(compatible_with_sync, _UnsetType) else compatible_with_sync,
        )
        validate_async_options(*options)
        with AudioUpload(audio) as source:
            upload = MultipartUpload(
                source, params, logging_opt_out=options[0], content_id=options[1], compatible_with_sync=options[2]
            )
            body = self._request("POST", url, upload, params)
        return parse_submission(body)

    def _url(self, override: str | _UnsetType) -> str:
        return self._api_url if isinstance(override, _UnsetType) else _endpoint(override)

    def _request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        body: MultipartUpload | None,
        params: RecognitionParams,
        *,
        session_id: str | None = None,
        deadline: float | None = None,
    ) -> bytes:
        try:
            status, response = self._transport.request(
                method, url, {"Authorization": f"Bearer {self._api_key}"}, body, params, deadline=deadline
            )
        except (OSError, http.client.HTTPException, ConnectionFailedError):
            if deadline is not None and self._clock() >= deadline:
                raise TimeoutError("Job deadline expired") from None
            message = "Async HTTP connection failed"
            if method == "POST":
                message += "; submission may have been accepted, automatic retry is disabled"
            raise ConnectionFailedError(message) from None
        if deadline is not None and self._clock() >= deadline:
            raise TimeoutError("Job deadline expired")
        if status != 200:
            raise AsyncHttpApiError(
                f"Async HTTP {method} failed with HTTP {status}", status_code=status, raw_body=response, session_id=session_id
            )
        return response

    def _fetch(self, session_id: str, url: str, params: RecognitionParams, deadline: float | None = None) -> AsyncJobSnapshot:
        body = self._request("GET", f"{url}/{quote(session_id, safe='')}", None, params, session_id=session_id, deadline=deadline)
        return parse_job(body, session_id)

    def get_job(
        self,
        session_id: str,
        *,
        api_url: str | _UnsetType = UNSET,
        proxy_server_name: str | None | _UnsetType = UNSET,
        connect_timeout: int | _UnsetType = UNSET,
        receive_timeout: int | _UnsetType = UNSET,
    ) -> AsyncJobSnapshot:
        """状態と結果を取得する、error状態もスナップショットとして返す

        Args:
            session_id (str): 保存したジョブID
            api_url (str | _UnsetType): 接続先の上書き
            proxy_server_name (str | None | _UnsetType): プロキシの上書き
            connect_timeout (int | _UnsetType): 接続待機のミリ秒
            receive_timeout (int | _UnsetType): 受信待機のミリ秒

        Returns:
            AsyncJobSnapshot: 認識結果又は処理中・失敗の状態
        """
        session_id = _job_id(session_id)
        params = resolve_recognition_overrides(self._params, locals())
        _communication(params)
        return self._fetch(session_id, self._url(api_url), params)

    def wait(  # noqa: PLR0913
        self,
        session_id: str,
        *,
        poll_interval: float = 10.0,
        timeout: float | None = None,
        raise_on_error: bool = True,
        api_url: str | _UnsetType = UNSET,
        proxy_server_name: str | None | _UnsetType = UNSET,
        connect_timeout: int | _UnsetType = UNSET,
        receive_timeout: int | _UnsetType = UNSET,
    ) -> AsyncJobSnapshot:
        """呼び出し元をブロックして終端状態を待つ、中断はジョブのキャンセルではない

        Args:
            session_id (str): 保存したジョブID
            poll_interval (float): 正のポーリング間隔、秒
            timeout (float | None): 全体の待機上限、秒、Noneのみ無制限
            raise_on_error (bool): ジョブ又は認識失敗を例外にするか
            api_url (str | _UnsetType): 接続先の上書き
            proxy_server_name (str | None | _UnsetType): プロキシの上書き
            connect_timeout (int | _UnsetType): 接続待機のミリ秒
            receive_timeout (int | _UnsetType): 受信待機のミリ秒

        Returns:
            AsyncJobSnapshot: 終端状態と認識結果

        Raises:
            AsyncJobTimeoutError: 待機上限を超えた場合、IDから再開できる
            AsyncJobError: raise_on_error=Trueでジョブ又は認識が失敗した場合
            AsyncHttpApiError: HTTPエラー又は不正応答、設定に関係なく送出
        """
        session_id = _job_id(session_id)
        interval = _seconds(poll_interval, "poll_interval")
        duration = None if timeout is None else _seconds(timeout, "timeout")
        if not isinstance(raise_on_error, bool):
            raise ConfigurationError("raise_on_error must be a boolean")
        params = resolve_recognition_overrides(self._params, locals())
        _communication(params)
        url = self._url(api_url)
        deadline = None if duration is None else self._clock() + duration
        snapshot = None
        while True:
            if deadline is not None and self._clock() >= deadline:
                raise AsyncJobTimeoutError(session_id, snapshot)
            try:
                snapshot = self._fetch(session_id, url, params, deadline)
            except TimeoutError:
                raise AsyncJobTimeoutError(session_id, snapshot) from None
            if deadline is not None and self._clock() >= deadline:
                raise AsyncJobTimeoutError(session_id, snapshot)
            if snapshot.is_terminal:
                if snapshot.is_error and raise_on_error:
                    raise AsyncJobError("Async HTTP job or recognition failed", snapshot)
                return snapshot
            remaining = interval if deadline is None else min(interval, max(0, deadline - self._clock()))
            self._sleep(remaining)
