"""公開APIから同期HTTPとWebSocketを直接利用する"""

import http.client
import os
from collections.abc import Sequence

from ._audio import resolve_audio
from ._connection_settings import parse_service_url
from ._http_recognition import HttpRecognitionConnection, HttpRecognitionTransport
from ._params import RecognitionParams
from ._recognition_settings import (
    _resolve_audio_filter_properties,
    _resolve_endpoint_url,
    _resolve_logging_opt_out,
    _resolve_profile_words,
    _resolve_segmenter_properties,
    _validate_custom_url_logging_opt_out,
    _validate_endpoint_url_type,
    _validate_logging_opt_out,
    resolve_recognition_overrides,
)
from ._request_parameters import build_http_multipart
from ._segmenter import SegmenterProperties
from ._stream import StreamConnectionManager
from ._types import AudioSource
from ._websocket_connection import WebSocketTransport
from .constants import Codec
from .dictionary import ProfileWord
from .exceptions import AuthenticationError, ConfigurationError, ConnectionFailedError, RecognitionError
from .models import RecognitionResult, parse_result
from .settings import USE_CLIENT_DEFAULT, UseClientDefault

_DEFAULT_HRP_URL = "https://acp-api.amivoice.com/v1/recognize"
_DEFAULT_WRP_URL = "wss://acp-api.amivoice.com/v1/"
_DEFAULT_NOLOG_HRP_URL = "https://acp-api.amivoice.com/v1/nolog/recognize"
_DEFAULT_NOLOG_WRP_URL = "wss://acp-api.amivoice.com/v1/nolog/"
_MAX_AUDIO_BYTES = 16_777_215


class AmiVoiceClient:
    """公式の認識設定を保持し、呼び出しごとに接続を生成する"""

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
        no_input_timeout: int | None = None,
        logging_opt_out: bool = False,
        http_api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        ws_api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        hrp_transport: HttpRecognitionTransport | None = None,
        wrp_transport: WebSocketTransport | None = None,
    ) -> None:
        """クライアントを初期化する、サーバの既定値は送信しない

        Args:
            api_key (str | None): 認証情報、省略時はAMIVOICE_API_KEY
            grammar_file_names (str | None): 接続エンジン名
            codec (Codec | str | None): 音声フォーマット
            proxy_server_name (str | None): HTTPプロキシ
            connect_timeout (int): 接続待機のミリ秒数、0は無制限
            receive_timeout (int): 受信待機のミリ秒数、0は無制限
            profile_id (str | None): ユーザー辞書の参照名
            profile_words (str | Sequence[ProfileWord] | None): セッションの単語登録
            segmenter (SegmenterProperties | None): 型付きの発話検出設定
            segmenter_properties (str | None): 発話検出設定の文字列
            selected_channel (int | tuple[int, int] | None): 単一チャネル又は0から始まる平均範囲
            audio_filter_properties (str | None): 同期HTTPのチャネル指定
            confidence_level (float | None): 信頼度しきい値、0から1
            keep_filler_token (bool | None): フィラーを残すか
            result_updated_interval (int | None): WebSocketの途中結果間隔、ミリ秒
            extension (str | None): 使用量集計のJSON設定
            billing_key (str | None): 使用量集計タグ
            recognition_timeout (int | None): 認識完了のタイムアウト、ミリ秒
            complete_timeout (int | None): ルール認識の確定待ち時間、ミリ秒
            wildcard_model_penalty (float | None): ルール認識のワイルドカードペナルティ
            max_decoding_time (int | None): 最大認識処理時間、ミリ秒
            max_response_time (int | None): 最大応答時間、ミリ秒
            max_decoding_rate (float | None): 最大の認識時間倍率
            target_response_time (int | None): 目標応答時間、ミリ秒
            target_decoding_rate (float | None): 目標の認識時間倍率
            no_input_timeout (int | None): WebSocketの発話開始待ち時間、ミリ秒
            logging_opt_out (bool): 音声ログを残さない接続先を使うか
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
        self._params = RecognitionParams(
            grammar_file_names=grammar_file_names,
            codec=codec,
            proxy_server_name=proxy_server_name,
            connect_timeout=connect_timeout,
            receive_timeout=receive_timeout,
            profile_id=profile_id,
            profile_words=_resolve_profile_words(profile_words),
            segmenter_properties=_resolve_segmenter_properties(segmenter, segmenter_properties),
            audio_filter_properties=_resolve_audio_filter_properties(selected_channel, audio_filter_properties),
            confidence_level=confidence_level,
            keep_filler_token=keep_filler_token,
            result_updated_interval=result_updated_interval,
            extension=extension,
            billing_key=billing_key,
            recognition_timeout=recognition_timeout,
            complete_timeout=complete_timeout,
            wildcard_model_penalty=wildcard_model_penalty,
            max_decoding_time=max_decoding_time,
            max_response_time=max_response_time,
            max_decoding_rate=max_decoding_rate,
            target_response_time=target_response_time,
            target_decoding_rate=target_decoding_rate,
            no_input_timeout=no_input_timeout,
        )
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
        grammar_file_names: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        codec: Codec | str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        proxy_server_name: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        connect_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        receive_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        profile_id: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        profile_words: str | Sequence[ProfileWord] | None | UseClientDefault = USE_CLIENT_DEFAULT,
        segmenter: SegmenterProperties | None | UseClientDefault = USE_CLIENT_DEFAULT,
        segmenter_properties: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        selected_channel: int | tuple[int, int] | None | UseClientDefault = USE_CLIENT_DEFAULT,
        audio_filter_properties: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        confidence_level: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        keep_filler_token: bool | None | UseClientDefault = USE_CLIENT_DEFAULT,
        extension: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        billing_key: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        recognition_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        complete_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        wildcard_model_penalty: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        max_decoding_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        max_response_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        max_decoding_rate: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        target_response_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        target_decoding_rate: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        raise_on_error: bool = True,
        api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        logging_opt_out: bool | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> RecognitionResult:
        """音声をmultipartで送信し、本文のcodeとmessageで成否を判断する

        Args:
            audio (AudioSource): bytes、ファイルパス、バイナリストリーム
            grammar_file_names (str | None | UseClientDefault): 接続エンジン名、未指定時は既定値を継承
            codec (Codec | str | None | UseClientDefault): 音声フォーマット、未指定時は既定値を継承
            proxy_server_name (str | None | UseClientDefault): HTTPプロキシ、未指定時は既定値を継承
            connect_timeout (int | UseClientDefault): 接続待機のミリ秒数、0は無制限、未指定時は既定値を継承
            receive_timeout (int | UseClientDefault): 受信待機のミリ秒数、0は無制限、未指定時は既定値を継承
            profile_id (str | None | UseClientDefault): ユーザー辞書の参照名、未指定時は既定値を継承
            profile_words (str | Sequence[ProfileWord] | None | UseClientDefault): セッションの単語登録、未指定時は既定値を継承
            segmenter (SegmenterProperties | None | UseClientDefault): 型付きの発話検出設定、未指定時は既定値を継承
            segmenter_properties (str | None | UseClientDefault): 発話検出設定の文字列、未指定時は既定値を継承
            selected_channel (int | tuple[int, int] | None | UseClientDefault): 単一チャネル又は0から始まる平均範囲
                未指定時は既定値を継承
            audio_filter_properties (str | None | UseClientDefault): 同期HTTPのチャネル指定、未指定時は既定値を継承
            confidence_level (float | None | UseClientDefault): 信頼度しきい値、0から1、未指定時は既定値を継承
            keep_filler_token (bool | None | UseClientDefault): フィラーを残すか、未指定時は既定値を継承
            extension (str | None | UseClientDefault): 使用量集計のJSON設定、未指定時は既定値を継承
            billing_key (str | None | UseClientDefault): 使用量集計タグ、未指定時は既定値を継承
            recognition_timeout (int | None | UseClientDefault): 認識完了のタイムアウト、ミリ秒、未指定時は既定値を継承
            complete_timeout (int | None | UseClientDefault): ルール認識の確定待ち時間、ミリ秒、未指定時は既定値を継承
            wildcard_model_penalty (float | None | UseClientDefault): ルール認識のワイルドカードペナルティ、未指定時は既定値を継承
            max_decoding_time (int | None | UseClientDefault): 最大認識処理時間、ミリ秒、未指定時は既定値を継承
            max_response_time (int | None | UseClientDefault): 最大応答時間、ミリ秒、未指定時は既定値を継承
            max_decoding_rate (float | None | UseClientDefault): 最大の認識時間倍率、未指定時は既定値を継承
            target_response_time (int | None | UseClientDefault): 目標応答時間、ミリ秒、未指定時は既定値を継承
            target_decoding_rate (float | None | UseClientDefault): 目標の認識時間倍率、未指定時は既定値を継承
            raise_on_error (bool): 認識失敗時に例外を送出するか
            api_url (str | UseClientDefault): 今回だけ使用するHTTP接続先
            logging_opt_out (bool | UseClientDefault): 今回だけのログ保存設定

        Returns:
            RecognitionResult: 成功又は失敗の認識結果

        Raises:
            ConfigurationError: 必須設定や音声サイズが不正な場合
            ConnectionFailedError: HTTP通信に失敗した場合
            RecognitionError: レスポンスが不正な場合や認識が失敗した場合
        """
        params = resolve_recognition_overrides(
            self._params,
            {
                "grammar_file_names": grammar_file_names,
                "codec": codec,
                "proxy_server_name": proxy_server_name,
                "connect_timeout": connect_timeout,
                "receive_timeout": receive_timeout,
                "profile_id": profile_id,
                "profile_words": profile_words,
                "segmenter": segmenter,
                "segmenter_properties": segmenter_properties,
                "selected_channel": selected_channel,
                "audio_filter_properties": audio_filter_properties,
                "confidence_level": confidence_level,
                "keep_filler_token": keep_filler_token,
                "extension": extension,
                "billing_key": billing_key,
                "recognition_timeout": recognition_timeout,
                "complete_timeout": complete_timeout,
                "wildcard_model_penalty": wildcard_model_penalty,
                "max_decoding_time": max_decoding_time,
                "max_response_time": max_response_time,
                "max_decoding_rate": max_decoding_rate,
                "target_response_time": target_response_time,
                "target_decoding_rate": target_decoding_rate,
            },
        )
        data = resolve_audio(audio)
        if not data or len(data) > _MAX_AUDIO_BYTES:
            raise ConfigurationError("Audio data must contain between 1 and 16777215 bytes")
        request = build_http_multipart(params, data)
        opt_out = _resolve_logging_opt_out(logging_opt_out, self._logging_opt_out)
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

    def stream(  # noqa: PLR0913
        self,
        *,
        grammar_file_names: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        codec: Codec | str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        proxy_server_name: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        connect_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        receive_timeout: int | UseClientDefault = USE_CLIENT_DEFAULT,
        profile_id: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        profile_words: str | Sequence[ProfileWord] | None | UseClientDefault = USE_CLIENT_DEFAULT,
        segmenter: SegmenterProperties | None | UseClientDefault = USE_CLIENT_DEFAULT,
        segmenter_properties: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        confidence_level: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        keep_filler_token: bool | None | UseClientDefault = USE_CLIENT_DEFAULT,
        result_updated_interval: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        extension: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        billing_key: str | None | UseClientDefault = USE_CLIENT_DEFAULT,
        recognition_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        complete_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        wildcard_model_penalty: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        max_decoding_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        max_response_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        max_decoding_rate: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        target_response_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        target_decoding_rate: float | None | UseClientDefault = USE_CLIENT_DEFAULT,
        no_input_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT,
        api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
        logging_opt_out: bool | UseClientDefault = USE_CLIENT_DEFAULT,
    ) -> StreamConnectionManager:
        """WebSocketの接続と認識セッションを管理するコンテキストを返す

        Args:
            grammar_file_names (str | None | UseClientDefault): 接続エンジン名、未指定時は既定値を継承
            codec (Codec | str | None | UseClientDefault): 音声フォーマット、未指定時は既定値を継承
            proxy_server_name (str | None | UseClientDefault): HTTPプロキシ、未指定時は既定値を継承
            connect_timeout (int | UseClientDefault): 接続待機のミリ秒数、0は無制限、未指定時は既定値を継承
            receive_timeout (int | UseClientDefault): 受信待機のミリ秒数、0は無制限、未指定時は既定値を継承
            profile_id (str | None | UseClientDefault): ユーザー辞書の参照名、未指定時は既定値を継承
            profile_words (str | Sequence[ProfileWord] | None | UseClientDefault): セッションの単語登録、未指定時は既定値を継承
            segmenter (SegmenterProperties | None | UseClientDefault): 型付きの発話検出設定、未指定時は既定値を継承
            segmenter_properties (str | None | UseClientDefault): 発話検出設定の文字列、未指定時は既定値を継承
            confidence_level (float | None | UseClientDefault): 信頼度しきい値、0から1、未指定時は既定値を継承
            keep_filler_token (bool | None | UseClientDefault): フィラーを残すか、未指定時は既定値を継承
            result_updated_interval (int | None | UseClientDefault): WebSocketの途中結果間隔、ミリ秒、未指定時は既定値を継承
            extension (str | None | UseClientDefault): 使用量集計のJSON設定、未指定時は既定値を継承
            billing_key (str | None | UseClientDefault): 使用量集計タグ、未指定時は既定値を継承
            recognition_timeout (int | None | UseClientDefault): 認識完了のタイムアウト、ミリ秒、未指定時は既定値を継承
            complete_timeout (int | None | UseClientDefault): ルール認識の確定待ち時間、ミリ秒、未指定時は既定値を継承
            wildcard_model_penalty (float | None | UseClientDefault): ルール認識のワイルドカードペナルティ、未指定時は既定値を継承
            max_decoding_time (int | None | UseClientDefault): 最大認識処理時間、ミリ秒、未指定時は既定値を継承
            max_response_time (int | None | UseClientDefault): 最大応答時間、ミリ秒、未指定時は既定値を継承
            max_decoding_rate (float | None | UseClientDefault): 最大の認識時間倍率、未指定時は既定値を継承
            target_response_time (int | None | UseClientDefault): 目標応答時間、ミリ秒、未指定時は既定値を継承
            target_decoding_rate (float | None | UseClientDefault): 目標の認識時間倍率、未指定時は既定値を継承
            no_input_timeout (int | None | UseClientDefault): WebSocketの発話開始待ち時間、ミリ秒、未指定時は既定値を継承
            api_url (str | UseClientDefault): 今回だけ使用するWebSocket接続先
            logging_opt_out (bool | UseClientDefault): 今回だけのログ保存設定

        Returns:
            StreamConnectionManager: withで接続を開始する管理オブジェクト
        """
        params = resolve_recognition_overrides(
            self._params,
            {
                "grammar_file_names": grammar_file_names,
                "codec": codec,
                "proxy_server_name": proxy_server_name,
                "connect_timeout": connect_timeout,
                "receive_timeout": receive_timeout,
                "profile_id": profile_id,
                "profile_words": profile_words,
                "segmenter": segmenter,
                "segmenter_properties": segmenter_properties,
                "confidence_level": confidence_level,
                "keep_filler_token": keep_filler_token,
                "result_updated_interval": result_updated_interval,
                "extension": extension,
                "billing_key": billing_key,
                "recognition_timeout": recognition_timeout,
                "complete_timeout": complete_timeout,
                "wildcard_model_penalty": wildcard_model_penalty,
                "max_decoding_time": max_decoding_time,
                "max_response_time": max_response_time,
                "max_decoding_rate": max_decoding_rate,
                "target_response_time": target_response_time,
                "target_decoding_rate": target_decoding_rate,
                "no_input_timeout": no_input_timeout,
            },
        )
        opt_out = _resolve_logging_opt_out(logging_opt_out, self._logging_opt_out)
        url = _resolve_endpoint_url(api_url, self._ws_api_url, self._ws_api_url_is_default, _DEFAULT_NOLOG_WRP_URL, opt_out)
        parse_service_url(url, ("ws", "wss"))
        return StreamConnectionManager(api_key=self._api_key, api_url=url, params=params, wrp_transport=self._wrp_transport)


def transcribe(  # noqa: PLR0913
    audio: AudioSource,
    *,
    api_key: str | None = None,
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
    complete_timeout: int | None = None,
    wildcard_model_penalty: float | None = None,
    max_decoding_time: int | None = None,
    max_response_time: int | None = None,
    max_decoding_rate: float | None = None,
    target_response_time: int | None = None,
    target_decoding_rate: float | None = None,
    logging_opt_out: bool = False,
    api_url: str | UseClientDefault = USE_CLIENT_DEFAULT,
    raise_on_error: bool = True,
    _transport: HttpRecognitionTransport | None = None,
) -> RecognitionResult:
    """クライアントを一時生成して同期HTTP認識する

    Args:
        audio (AudioSource): 入力音声
        api_key (str | None): 認証情報、省略時はAMIVOICE_API_KEY
        grammar_file_names (str | None): 接続エンジン名
        codec (Codec | str | None): 音声フォーマット
        proxy_server_name (str | None): HTTPプロキシ
        connect_timeout (int): 接続待機のミリ秒数、0は無制限
        receive_timeout (int): 受信待機のミリ秒数、0は無制限
        profile_id (str | None): ユーザー辞書の参照名
        profile_words (str | Sequence[ProfileWord] | None): セッションの単語登録
        segmenter (SegmenterProperties | None): 型付きの発話検出設定
        segmenter_properties (str | None): 発話検出設定の文字列
        selected_channel (int | tuple[int, int] | None): 単一チャネル又は0から始まる平均範囲
        audio_filter_properties (str | None): 同期HTTPのチャネル指定
        confidence_level (float | None): 信頼度しきい値、0から1
        keep_filler_token (bool | None): フィラーを残すか
        extension (str | None): 使用量集計のJSON設定
        billing_key (str | None): 使用量集計タグ
        recognition_timeout (int | None): 認識完了のタイムアウト、ミリ秒
        complete_timeout (int | None): ルール認識の確定待ち時間、ミリ秒
        wildcard_model_penalty (float | None): ルール認識のワイルドカードペナルティ
        max_decoding_time (int | None): 最大認識処理時間、ミリ秒
        max_response_time (int | None): 最大応答時間、ミリ秒
        max_decoding_rate (float | None): 最大の認識時間倍率
        target_response_time (int | None): 目標応答時間、ミリ秒
        target_decoding_rate (float | None): 目標の認識時間倍率
        logging_opt_out (bool): ログを残さない接続先を使うか
        api_url (str | UseClientDefault): 同期HTTP接続先
        raise_on_error (bool): 認識失敗時に例外を送出するか
        _transport (HttpRecognitionTransport | None): テスト用注入口

    Returns:
        RecognitionResult: 認識結果
    """
    client = AmiVoiceClient(
        api_key,
        grammar_file_names=grammar_file_names,
        codec=codec,
        proxy_server_name=proxy_server_name,
        connect_timeout=connect_timeout,
        receive_timeout=receive_timeout,
        profile_id=profile_id,
        profile_words=profile_words,
        segmenter=segmenter,
        segmenter_properties=segmenter_properties,
        selected_channel=selected_channel,
        audio_filter_properties=audio_filter_properties,
        confidence_level=confidence_level,
        keep_filler_token=keep_filler_token,
        extension=extension,
        billing_key=billing_key,
        recognition_timeout=recognition_timeout,
        complete_timeout=complete_timeout,
        wildcard_model_penalty=wildcard_model_penalty,
        max_decoding_time=max_decoding_time,
        max_response_time=max_response_time,
        max_decoding_rate=max_decoding_rate,
        target_response_time=target_response_time,
        target_decoding_rate=target_decoding_rate,
        http_api_url=api_url,
        logging_opt_out=logging_opt_out,
        hrp_transport=_transport,
    )
    return client.transcribe(audio, raise_on_error=raise_on_error)
