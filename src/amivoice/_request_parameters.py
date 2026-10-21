"""公式パラメータ一覧からHTTP本文とWebSocket開始コマンドを生成する"""

import re
import secrets
from dataclasses import dataclass
from urllib.parse import quote

from ._billing import resolve_billing_extension
from ._params import RecognitionParams
from .constants import Codec, Engine
from .exceptions import ConfigurationError

# 送信パラメータ名と対応インタフェースはここだけで定義する
# https://docs.amivoice.com/amivoice-api/manual/request-parameters
REQUEST_PARAMETERS = {
    "api_key": ("authorization", "ws"),
    "grammar_file_names": ("grammarFileNames", "http"),
    "profile_id": ("profileId", "both"),
    "profile_words": ("profileWords", "both"),
    "keep_filler_token": ("keepFillerToken", "both"),
    "segmenter_properties": ("segmenterProperties", "both"),
    "extension": ("extension", "both"),
    "max_decoding_time": ("maxDecodingTime", "both"),
    "max_response_time": ("maxResponseTime", "both"),
    "max_decoding_rate": ("maxDecodingRate", "both"),
    "target_response_time": ("targetResponseTime", "both"),
    "target_decoding_rate": ("targetDecodingRate", "both"),
    "recognition_timeout": ("recognitionTimeout", "both"),
    "confidence_level": ("confidenceLevel", "both"),
    "complete_timeout": ("completeTimeout", "both"),
    "wildcard_model_penalty": ("wildcardModelPenalty", "both"),
    "audio_filter_properties": ("audioFilterProperties", "http"),
    "result_updated_interval": ("resultUpdatedInterval", "ws"),
    "no_input_timeout": ("noInputTimeout", "ws"),
}
SEGMENTER_KEYS = frozenset(
    {
        "threshold",
        "preTime",
        "postTime",
        "preForcedTime",
        "postForcedTime",
        "powerThreshold",
        "decayTime",
        "useDiarizer",
        "diarizerAlpha",
        "diarizerTransitionBias",
        "useLid",
    }
)
_CHANNEL_PATTERN = re.compile(r"selectedChannel=(0|[1-9][0-9]*|0-[1-9][0-9]*)\Z")


@dataclass(frozen=True)
class HttpMultipartRequest:
    """音声パートを末尾に配置したmultipart本文"""

    body: bytes
    content_type: str


def _check_text(value: str) -> str:
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ConfigurationError("Recognition parameter must be a string without control characters")
    return value


def validate_recognition_request(params: RecognitionParams) -> None:
    """エンジンと追加設定が公式の対象範囲に収まることを確認する

    Args:
        params (RecognitionParams): 認識設定

    Raises:
        ConfigurationError: 必須設定がない場合や未掲載設定を含む場合
    """
    if not params.grammar_file_names:
        raise ConfigurationError("grammar_file_names is required")
    engine = _check_text(params.grammar_file_names).split("|", 1)[0]
    if not engine:
        raise ConfigurationError("grammar_file_names engine is required")
    if params.codec is not None:
        try:
            Codec(params.codec)
        except (ValueError, TypeError):
            raise ConfigurationError("codec must be an official audio format") from None
    if params.keep_filler_token is not None and engine in {item.value for item in Engine if item.name.startswith("A2")}:
        raise ConfigurationError("keep_filler_token is not supported by End to End engines")
    if " " in engine:
        raise ConfigurationError("grammar_file_names engine must not contain spaces")
    if (params.complete_timeout is not None or params.wildcard_model_penalty is not None) and engine != "-a-rule-input-private":
        raise ConfigurationError("Recognition rule parameters require -a-rule-input-private")
    if params.segmenter_properties is not None:
        for property_value in _check_text(params.segmenter_properties).split():
            key, separator, value = property_value.partition("=")
            if key not in SEGMENTER_KEYS or not separator or not value:
                raise ConfigurationError("Unsupported segmenter_properties parameter")
    if params.audio_filter_properties is not None and not _CHANNEL_PATTERN.fullmatch(_check_text(params.audio_filter_properties)):
        raise ConfigurationError("audio_filter_properties must select one channel or a range starting at 0")


def _request_values(params: RecognitionParams, interface: str) -> list[tuple[str, str]]:
    validate_recognition_request(params)
    if interface == "async_http":
        unsupported = ("complete_timeout", "wildcard_model_penalty", "result_updated_interval", "no_input_timeout")
        if any(getattr(params, field) is not None for field in unsupported):
            raise ConfigurationError("Recognition parameter is not supported by async HTTP")
        for property_value in (params.segmenter_properties or "").split():
            if property_value.partition("=")[0] in ("useDiarizer", "diarizerAlpha", "diarizerTransitionBias"):
                raise ConfigurationError("Segmenter diarization is not supported by async HTTP")
        # v2のaudioFilterPropertiesを含み、HTTP共通項目だけを再利用する
        interface = "http"
    values = []
    for field, (key, scope) in REQUEST_PARAMETERS.items():
        if field == "api_key" or scope not in ("both", interface):
            continue
        value = (
            resolve_billing_extension(params.extension, params.billing_key) if field == "extension" else getattr(params, field)
        )
        if value is None:
            continue
        text = str(int(value)) if isinstance(value, bool) else str(value)
        values.append((key, _check_text(text)))
    return values


def _encode_http_value(key: str, value: str) -> str:
    # グラマ本文のBase64部分だけは公式にURLエンコード不要とされる
    # https://docs.amivoice.com/amivoice-api/manual/set-grammar-file
    if key == REQUEST_PARAMETERS["grammar_file_names"][0] and "|" in value:
        parts = value.split("|")
        return "%7C".join(part if re.fullmatch(r"H4sI[A-Za-z0-9+/]*={0,2}", part) else quote(part, safe="") for part in parts)
    return quote(value, safe="")


def build_http_multipart(
    params: RecognitionParams, audio: bytes, *, api_key: str | None = None, boundary: str | None = None
) -> HttpMultipartRequest:
    """同期HTTPのu/d/c/aだけを生成し、aを最後にする

    Args:
        params (RecognitionParams): 認識設定
        audio (bytes): 音声データ
        api_key (str | None): uパートに入れる認証情報、ヘッダ認証時は省略
        boundary (str | None): テスト用境界文字列、省略時はランダム生成

    Returns:
        HttpMultipartRequest: 本文とContent-Type

    Raises:
        ConfigurationError: 設定や境界文字列が不正な場合
    """
    boundary = boundary or secrets.token_hex(24)
    if re.fullmatch(r"[A-Za-z0-9_-]{1,70}", boundary) is None:
        raise ConfigurationError("Multipart boundary must contain only ASCII letters, digits, '-' or '_'")
    values = _request_values(params, "http")
    fields = []
    if api_key is not None:
        fields.append(("u", _check_text(api_key)))
    fields.append(("d", " ".join(f"{key}={_encode_http_value(key, value)}" for key, value in values)))
    if params.codec is not None and Codec(params.codec) not in (Codec.HEADER_8K, Codec.HEADER_16K):
        fields.append(("c", Codec(params.codec).value))
    chunks = []
    for key, value in fields:
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    chunks.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="a"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
    )
    chunks.extend((audio, f"\r\n--{boundary}--\r\n".encode()))
    return HttpMultipartRequest(b"".join(chunks), f"multipart/form-data; boundary={boundary}")


def _quote_websocket_value(value: str) -> str:
    text = _check_text(value)
    if " " in text or '"' in text or not text:
        return '"' + text.replace('"', '""') + '"'
    return text


def build_start_command(params: RecognitionParams, *, api_key: str | None = None) -> str:
    """公式sコマンドを生成し、ヘッダ認証時は認証情報を含めない

    Args:
        params (RecognitionParams): 認識設定
        api_key (str | None): コマンド認証を使う場合だけ指定

    Returns:
        str: UTF-8で送る開始コマンド

    Raises:
        ConfigurationError: 必須設定がない場合やHTTP専用設定がある場合
    """
    if params.audio_filter_properties is not None:
        raise ConfigurationError("audio_filter_properties is not supported by stream()")
    if params.codec is None:
        raise ConfigurationError("codec is required for stream()")
    values = _request_values(params, "ws")
    parts = ["s", Codec(params.codec).value, _quote_websocket_value(params.grammar_file_names)]
    if api_key is not None:
        values.insert(0, (REQUEST_PARAMETERS["api_key"][0], _check_text(api_key)))
    parts.extend(f"{key}={_quote_websocket_value(value)}" for key, value in values)
    return " ".join(parts)
