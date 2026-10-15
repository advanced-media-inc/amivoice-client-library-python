"""AmiVoiceの非同期HTTP v2を通常の同期メソッドから利用する"""

import http.client
import ipaddress
import math
import os
import time
from dataclasses import replace
from urllib.parse import quote

from ._async_audio import AudioUpload, MultipartUpload, validate_async_options
from ._async_http_transport import AsyncHttpConnection, AsyncHttpTransport
from ._async_models import parse_job, parse_submission
from ._connection_settings import parse_http_proxy, parse_service_url
from ._http_api import validate_service_api_key
from ._params import RecognitionParams
from ._recognition_settings import merge_recognition_settings, resolve_recognition_overrides, settings_to_params
from ._request_parameters import _request_values
from ._types import AudioSource
from .async_models import AsyncJobSnapshot, AsyncJobSubmission
from .exceptions import (
    AsyncHttpApiError,
    AsyncHttpAuthenticationError,
    AsyncJobError,
    AsyncJobTimeoutError,
    ConfigurationError,
    ConnectionFailedError,
)
from .settings import USE_CLIENT_DEFAULT, RecognitionSettings, UseClientDefault

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
        settings: RecognitionSettings | None = None,
        proxy_server_name: str | None = None,
        connect_timeout: int = 0,
        receive_timeout: int = 0,
        api_url: str = _DEFAULT_URL,
        transport: AsyncHttpTransport | None = None,
    ) -> None:
        """認識設定と非同期HTTPの接続先を保持する

        Args:
            settings (RecognitionSettings | None): 認識設定、未指定は継承、Noneは全認識設定を解除
            api_key (str | None): Bearer認証情報、省略時はAMIVOICE_API_KEY
            proxy_server_name (str | None): HTTPプロキシ
            connect_timeout (int): 接続待機のミリ秒、0は無制限
            receive_timeout (int): ソケット送受信待機のミリ秒、0は無制限
            api_url (str): v2エンドポイント、HTTPS又はローカルHTTP
            transport (AsyncHttpTransport | None): テスト用の通信処理
        """
        self._api_key = validate_service_api_key(api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY"))
        self._settings = merge_recognition_settings(RecognitionSettings(), settings)
        self._params = RecognitionParams(
            proxy_server_name=proxy_server_name, connect_timeout=connect_timeout, receive_timeout=receive_timeout
        )
        params = settings_to_params(self._settings, self._params)
        _communication(params)
        if params.grammar_file_names is not None:
            _request_values(params, "async_http")
        self._options(self._settings)
        self._api_url = _endpoint(api_url)
        self._transport = transport if transport is not None else AsyncHttpConnection()
        self._clock = time.monotonic
        self._sleep = time.sleep

    @staticmethod
    def _options(settings: RecognitionSettings) -> tuple[bool | None, str | None, bool | None]:
        options = (
            None if settings.logging_opt_out is USE_CLIENT_DEFAULT else settings.logging_opt_out,
            None if settings.content_id is USE_CLIENT_DEFAULT else settings.content_id,
            None if settings.compatible_with_sync is USE_CLIENT_DEFAULT else settings.compatible_with_sync,
        )
        validate_async_options(*options)
        return options

    def submit(  # noqa: PLR0913
        self,
        audio: AudioSource,
        *,
        settings: RecognitionSettings | None | UseClientDefault = USE_CLIENT_DEFAULT,
        proxy_server_name: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        connect_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        receive_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> AsyncJobSubmission:
        """音声を登録し、認識完了を待たず受付済みIDを返す

        未指定の引数はコンストラクタの設定を継承し、任意設定のNoneは送信を解除する
        通信失敗時に受理済みか分からないため、音声を自動再送しない

        Args:
            settings (RecognitionSettings | None | UseClientDefault): 認識設定、未指定は継承、Noneは全認識設定を解除
            audio (AudioSource): bytes、Path、ファイルパス、バイナリストリーム
            proxy_server_name (str | None | UseClientDefault): HTTPプロキシ
            connect_timeout (int | UseClientDefault): 接続待機のミリ秒
            receive_timeout (int | UseClientDefault): 送受信待機のミリ秒
            api_url (str | UseClientDefault): 今回だけ使用する接続先

        Returns:
            AsyncJobSubmission: 受付済みジョブID、元の応答、ローカル音声サイズとMD5

        Raises:
            ConfigurationError: 認識設定又は音声サイズが不正な場合
            AsyncHttpApiError: 受付失敗、HTTPエラー、不正応答
            ConnectionFailedError: 通信失敗、ジョブが受理された可能性がある
        """
        configured = merge_recognition_settings(self._settings, settings)
        params = settings_to_params(configured, resolve_recognition_overrides(self._params, locals()))
        _request_values(params, "async_http")
        _communication(params)
        url = self._url(api_url)
        options = self._options(configured)
        with AudioUpload(audio) as source:
            upload = MultipartUpload(
                source, params, logging_opt_out=options[0], content_id=options[1], compatible_with_sync=options[2]
            )
            body = self._request("POST", url, upload, params)
            return replace(parse_submission(body), audio_size=source.size, audio_md5=source.audio_md5)

    def _url(self, override: str | UseClientDefault) -> str:
        return self._api_url if isinstance(override, UseClientDefault) else _endpoint(override)

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
            error_type = AsyncHttpAuthenticationError if status == 401 else AsyncHttpApiError
            raise error_type(
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
        api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        proxy_server_name: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        connect_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        receive_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> AsyncJobSnapshot:
        """状態と結果を取得する、error状態もスナップショットとして返す

        Args:
            session_id (str): 保存したジョブID
            api_url (str | UseClientDefault): 接続先の上書き
            proxy_server_name (str | None | UseClientDefault): プロキシの上書き
            connect_timeout (int | UseClientDefault): 接続待機のミリ秒
            receive_timeout (int | UseClientDefault): 受信待機のミリ秒

        Returns:
            AsyncJobSnapshot: 認識結果又は処理中・失敗の状態
        """
        session_id = _job_id(session_id)
        params = resolve_recognition_overrides(self._params, locals())
        _communication(params)
        return self._fetch(session_id, self._url(api_url), params)

    def _fetch_with_retries(  # noqa: PLR0913
        self,
        session_id: str,
        url: str,
        params: RecognitionParams,
        deadline: float | None,
        max_retries: int,
        retry_backoff: float,
    ) -> AsyncJobSnapshot:
        """一時的なGET失敗だけを全体期限内で再試行する

        Args:
            session_id (str): ジョブID
            url (str): 接続先
            params (RecognitionParams): 通信設定
            deadline (float | None): 全体待機期限
            max_retries (int): 連続失敗時の追加GET上限
            retry_backoff (float): 初回の待機秒数

        Returns:
            AsyncJobSnapshot: 正常に取得した状態

        Raises:
            AsyncHttpApiError: 再試行対象外又は上限到達のHTTPエラー
            ConnectionFailedError: 再試行上限到達の通信エラー
            TimeoutError: 全体待機期限を超えた場合
        """
        delay = min(retry_backoff, 30.0)
        for attempt in range(max_retries + 1):
            if deadline is not None and self._clock() >= deadline:
                raise TimeoutError("Job deadline expired")
            try:
                return self._fetch(session_id, url, params, deadline)
            except (AsyncHttpApiError, ConnectionFailedError) as error:
                if isinstance(error, AsyncHttpApiError) and error.status_code not in (429, 500, 502, 503, 504):
                    raise
                if attempt == max_retries:
                    raise
                remaining = delay if deadline is None else min(delay, max(0, deadline - self._clock()))
                self._sleep(remaining)
                delay = min(delay * 2, 30.0)
        raise AssertionError("Retry loop must return or raise")

    def wait(  # noqa: PLR0913
        self,
        session_id: str,
        *,
        poll_interval: float = 10.0,
        timeout: float | None = None,
        raise_on_error: bool = True,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        proxy_server_name: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        connect_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        receive_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> AsyncJobSnapshot:
        """呼び出し元をブロックして終端状態を待つ、中断はジョブのキャンセルではない

        Args:
            session_id (str): 保存したジョブID
            poll_interval (float): 正のポーリング間隔、秒
            timeout (float | None): 全体の待機上限、秒、Noneのみ無制限
            raise_on_error (bool): ジョブ又は認識失敗を例外にするか
            max_retries (int): GET連続失敗時の追加試行上限、0で再試行なし
            retry_backoff (float): GET再試行の初回待機秒数、倍増して最大30秒
            api_url (str | UseClientDefault): 接続先の上書き
            proxy_server_name (str | None | UseClientDefault): プロキシの上書き
            connect_timeout (int | UseClientDefault): 接続待機のミリ秒
            receive_timeout (int | UseClientDefault): 受信待機のミリ秒

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
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ConfigurationError("max_retries must be a non-negative integer")
        backoff = _seconds(retry_backoff, "retry_backoff")
        params = resolve_recognition_overrides(self._params, locals())
        _communication(params)
        url = self._url(api_url)
        deadline = None if duration is None else self._clock() + duration
        snapshot = None
        while True:
            if deadline is not None and self._clock() >= deadline:
                raise AsyncJobTimeoutError(session_id, snapshot)
            try:
                snapshot = self._fetch_with_retries(session_id, url, params, deadline, max_retries, backoff)
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
