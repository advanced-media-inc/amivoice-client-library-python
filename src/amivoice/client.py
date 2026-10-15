"""公開APIから同期HTTPとWebSocketを直接利用する"""

import http.client
import os

from ._audio import resolve_audio
from ._connection_settings import parse_service_url
from ._http_recognition import HttpRecognitionConnection, HttpRecognitionTransport
from ._params import RecognitionParams
from ._recognition_settings import (
    _resolve_endpoint_url,
    _validate_custom_url_logging_opt_out,
    _validate_endpoint_url_type,
    _validate_logging_opt_out,
    merge_recognition_settings,
    resolve_recognition_overrides,
    settings_to_params,
)
from ._request_parameters import build_http_multipart
from ._stream import StreamConnectionManager
from ._types import AudioSource
from ._websocket_connection import WebSocketTransport
from .exceptions import AuthenticationError, ConfigurationError, ConnectionFailedError, RecognitionError
from .models import RecognitionResult, parse_result
from .settings import USE_CLIENT_DEFAULT, RecognitionSettings, UseClientDefault

_DEFAULT_HRP_URL = "https://acp-api.amivoice.com/v1/recognize"
_DEFAULT_WRP_URL = "wss://acp-api.amivoice.com/v1/"
_DEFAULT_NOLOG_HRP_URL = "https://acp-api.amivoice.com/v1/nolog/recognize"
_DEFAULT_NOLOG_WRP_URL = "wss://acp-api.amivoice.com/v1/nolog/"
_MAX_AUDIO_BYTES = 16_777_215


def _validate_sync_options(settings: RecognitionSettings) -> None:
    if any(getattr(settings, name) not in (USE_CLIENT_DEFAULT, None) for name in ("content_id", "compatible_with_sync")):
        raise ConfigurationError("content_id and compatible_with_sync require async HTTP")


class AmiVoiceClient:
    """公式の認識設定を保持し、呼び出しごとに接続を生成する"""

    def __init__(  # noqa: PLR0913
        self,
        api_key: str | None = None,
        *,
        settings: RecognitionSettings | None = None,
        proxy_server_name: str | None = None,
        connect_timeout: int = 0,
        receive_timeout: int = 0,
        http_api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        ws_api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        hrp_transport: HttpRecognitionTransport | None = None,
        wrp_transport: WebSocketTransport | None = None,
    ) -> None:
        """クライアントを初期化する、サーバの既定値は送信しない

        Args:
            settings (RecognitionSettings | None): 認識設定、未指定は継承、Noneは全認識設定を解除
            api_key (str | None): 認証情報、省略時はAMIVOICE_API_KEY
            proxy_server_name (str | None): HTTPプロキシ
            connect_timeout (int): 接続待機のミリ秒数、0は無制限
            receive_timeout (int): 受信待機のミリ秒数、0は無制限
            http_api_url (str | UseClientDefault): 同期HTTPの接続先
            ws_api_url (str | UseClientDefault): WebSocketの接続先
            hrp_transport (HttpRecognitionTransport | None): HTTPのテスト注入口
            wrp_transport (WebSocketTransport | None): WebSocketのテスト注入口

        Raises:
            AuthenticationError: 認証情報が指定されていない場合
            ConfigurationError: 設定の型や組み合わせが不正な場合
        """
        resolved_key = api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY")
        if not resolved_key:
            raise AuthenticationError("AMIVOICE_API_KEY is not set")
        if (
            not isinstance(resolved_key, str)
            or not resolved_key.isascii()
            or any(ord(c) <= 32 or ord(c) == 127 for c in resolved_key)
        ):
            raise ConfigurationError("API key must contain printable ASCII characters without whitespace")
        self._api_key = resolved_key
        self._settings = merge_recognition_settings(RecognitionSettings(), settings)
        self._params = RecognitionParams(
            proxy_server_name=proxy_server_name, connect_timeout=connect_timeout, receive_timeout=receive_timeout
        )
        _validate_sync_options(self._settings)
        settings_to_params(self._settings, self._params)
        logging_opt_out = self._settings.logging_opt_out
        if logging_opt_out is USE_CLIENT_DEFAULT:
            logging_opt_out = False
        _validate_endpoint_url_type(http_api_url, "http_api_url")
        _validate_endpoint_url_type(ws_api_url, "ws_api_url")
        self._http_api_url_is_default = isinstance(http_api_url, UseClientDefault)
        self._ws_api_url_is_default = isinstance(ws_api_url, UseClientDefault)
        self._http_api_url = _DEFAULT_HRP_URL if http_api_url is USE_CLIENT_DEFAULT else http_api_url
        self._ws_api_url = _DEFAULT_WRP_URL if ws_api_url is USE_CLIENT_DEFAULT else ws_api_url
        parse_service_url(self._http_api_url, ("https", "http"))
        parse_service_url(self._ws_api_url, ("wss", "ws"))
        self._logging_opt_out = _validate_logging_opt_out(logging_opt_out)
        if logging_opt_out:
            if not self._http_api_url_is_default:
                _validate_custom_url_logging_opt_out(self._http_api_url, _DEFAULT_NOLOG_HRP_URL)
            if not self._ws_api_url_is_default:
                _validate_custom_url_logging_opt_out(self._ws_api_url, _DEFAULT_NOLOG_WRP_URL)
        self._hrp_transport = hrp_transport
        self._wrp_transport = wrp_transport

    def transcribe(  # noqa: PLR0913
        self,
        audio: AudioSource,
        *,
        settings: RecognitionSettings | None | UseClientDefault = USE_CLIENT_DEFAULT,
        proxy_server_name: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        connect_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        receive_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        raise_on_error: bool = True,
        api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> RecognitionResult:
        """音声をmultipartで送信し、本文のcodeとmessageで成否を判断する

        Args:
            settings (RecognitionSettings | None | UseClientDefault): 認識設定、未指定は継承、Noneは全認識設定を解除
            audio (AudioSource): bytes、ファイルパス、バイナリストリーム
            proxy_server_name (str | None | UseClientDefault): HTTPプロキシ、未指定時は既定値を継承
            connect_timeout (int | UseClientDefault): 接続待機のミリ秒数、0は無制限、未指定時は既定値を継承
            receive_timeout (int | UseClientDefault): 受信待機のミリ秒数、0は無制限、未指定時は既定値を継承
            raise_on_error (bool): 認識失敗時に例外を送出するか
            api_url (str | UseClientDefault): 今回だけ使用するHTTP接続先

        Returns:
            RecognitionResult: 成功又は失敗の認識結果

        Raises:
            ConfigurationError: 必須設定や音声サイズが不正な場合
            ConnectionFailedError: HTTP通信に失敗した場合
            RecognitionError: レスポンスが不正な場合や認識が失敗した場合
        """
        configured = merge_recognition_settings(self._settings, settings)
        _validate_sync_options(configured)
        params = settings_to_params(configured, resolve_recognition_overrides(self._params, locals()))
        logging_opt_out = configured.logging_opt_out
        if logging_opt_out is USE_CLIENT_DEFAULT:
            logging_opt_out = False
        data = resolve_audio(audio)
        if not data or len(data) > _MAX_AUDIO_BYTES:
            raise ConfigurationError("Audio data must contain between 1 and 16777215 bytes")
        request = build_http_multipart(params, data)
        opt_out = _validate_logging_opt_out(logging_opt_out)
        url = _resolve_endpoint_url(api_url, self._http_api_url, self._http_api_url_is_default, _DEFAULT_NOLOG_HRP_URL, opt_out)
        parse_service_url(url, ("http", "https"))
        transport = self._hrp_transport if self._hrp_transport is not None else HttpRecognitionConnection()
        try:
            status, body = transport.request(
                url, {"Authorization": f"Bearer {self._api_key}", "Content-Type": request.content_type}, request.body, params
            )
        except (OSError, http.client.HTTPException):
            raise ConnectionFailedError("HTTP recognition connection failed") from None
        if status != 200:
            raise RecognitionError(f"HTTP recognition request failed with status {status}")
        try:
            raw = body.decode("utf-8")
        except UnicodeDecodeError:
            raise RecognitionError("HTTP recognition result must be UTF-8") from None
        result = parse_result(raw, raise_on_error=False)
        if any(not isinstance(result.data.get(key), str) for key in ("code", "message", "text")):
            raise RecognitionError("HTTP recognition result is missing code, message or text")
        if not result.is_error and not result.text:
            raise RecognitionError("HTTP recognition success result contains no text")
        if result.is_error and raise_on_error:
            message = str(result.data.get("message") or result.data.get("code"))
            raise RecognitionError(message.replace(self._api_key, "[redacted]"), result=result)
        return result

    def stream(
        self,
        *,
        settings: RecognitionSettings | None | UseClientDefault = USE_CLIENT_DEFAULT,
        proxy_server_name: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        connect_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        receive_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> StreamConnectionManager:
        """WebSocketの接続と認識セッションを管理するコンテキストを返す

        Args:
            settings (RecognitionSettings | None | UseClientDefault): 認識設定、未指定は継承、Noneは全認識設定を解除
            proxy_server_name (str | None | UseClientDefault): HTTPプロキシ、未指定時は既定値を継承
            connect_timeout (int | UseClientDefault): 接続待機のミリ秒数、0は無制限、未指定時は既定値を継承
            receive_timeout (int | UseClientDefault): 受信待機のミリ秒数、0は無制限、未指定時は既定値を継承
            api_url (str | UseClientDefault): 今回だけ使用するWebSocket接続先

        Returns:
            StreamConnectionManager: withで接続を開始する管理オブジェクト
        """
        configured = merge_recognition_settings(self._settings, settings)
        _validate_sync_options(configured)
        params = settings_to_params(configured, resolve_recognition_overrides(self._params, locals()))
        logging_opt_out = configured.logging_opt_out
        if logging_opt_out is USE_CLIENT_DEFAULT:
            logging_opt_out = False
        opt_out = _validate_logging_opt_out(logging_opt_out)
        url = _resolve_endpoint_url(api_url, self._ws_api_url, self._ws_api_url_is_default, _DEFAULT_NOLOG_WRP_URL, opt_out)
        parse_service_url(url, ("ws", "wss"))
        return StreamConnectionManager(api_key=self._api_key, api_url=url, params=params, wrp_transport=self._wrp_transport)


def transcribe(  # noqa: PLR0913
    audio: AudioSource,
    *,
    settings: RecognitionSettings | None = None,
    api_key: str | None = None,
    proxy_server_name: str | None = None,
    connect_timeout: int = 0,
    receive_timeout: int = 0,
    api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
    raise_on_error: bool = True,
    _transport: HttpRecognitionTransport | None = None,
) -> RecognitionResult:
    """クライアントを一時生成して同期HTTP認識する

    Args:
        settings (RecognitionSettings | None): 認識設定、未指定は継承、Noneは全認識設定を解除
        audio (AudioSource): 入力音声
        api_key (str | None): 認証情報、省略時はAMIVOICE_API_KEY
        proxy_server_name (str | None): HTTPプロキシ
        connect_timeout (int): 接続待機のミリ秒数、0は無制限
        receive_timeout (int): 受信待機のミリ秒数、0は無制限
        api_url (str | UseClientDefault): 同期HTTP接続先
        raise_on_error (bool): 認識失敗時に例外を送出するか
        _transport (HttpRecognitionTransport | None): テスト用注入口

    Returns:
        RecognitionResult: 認識結果
    """
    client = AmiVoiceClient(
        api_key,
        settings=settings,
        proxy_server_name=proxy_server_name,
        connect_timeout=connect_timeout,
        receive_timeout=receive_timeout,
        http_api_url=api_url,
        hrp_transport=_transport,
    )
    return client.transcribe(audio, raise_on_error=raise_on_error)
