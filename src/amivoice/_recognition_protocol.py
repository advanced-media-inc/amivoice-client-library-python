"""AmiVoice 固有の HRP 電文と WRP コマンド・イベント変換

通信、接続状態、スレッドを持たず、不変の RecognitionParams を直接扱う
"""

import uuid
from dataclasses import dataclass
from urllib.parse import quote

from ._billing import resolve_billing_extension
from ._params import RecognitionParams
from .exceptions import RecognitionError
from .models import NotificationEvent, StreamEvent, UtteranceEvent, parse_result

# 設定フィールドと電文キーの対応はこの境界だけで管理する
_DOMAIN_FIELDS = (
    ("grammar_file_names", "grammarFileNames"),
    ("complete_timeout", "completeTimeout"),
    ("wildcard_model_penalty", "wildcardModelPenalty"),
    ("mode", "mode"),
    ("profile_id", "profileId"),
    ("profile_words", "profileWords"),
    ("segmenter_type", "segmenterType"),
    ("segmenter_properties", "segmenterProperties"),
    ("audio_filter_properties", "audioFilterProperties"),
    ("keep_filler_token", "keepFillerToken"),
    ("result_updated_interval", "resultUpdatedInterval"),
    ("max_decoding_time", "maxDecodingTime"),
    ("max_response_time", "maxResponseTime"),
    ("max_decoding_rate", "maxDecodingRate"),
    ("target_response_time", "targetResponseTime"),
    ("target_decoding_rate", "targetDecodingRate"),
    ("recognition_timeout", "recognitionTimeout"),
    ("confidence_level", "confidenceLevel"),
    ("extension", "extension"),
)


def _parameter_string(value: object) -> str:
    """真偽値を小文字、数値を丸めずに電文へ変換する"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def recognition_wire_values(params: RecognitionParams) -> dict[str, str]:
    """共通認識設定を電文キーへ変換し、未指定値だけを除外する

    Args:
        params (RecognitionParams): 解決済み認識設定

    Returns:
        dict[str, str]: エンコード前の電文値
    """
    values = {wire: _parameter_string(value) for field, wire in _DOMAIN_FIELDS if (value := getattr(params, field)) is not None}
    extension = resolve_billing_extension(params.extension, params.billing_key)
    if extension is not None:
        values["extension"] = extension
    return values


def build_hrp_domain(params: RecognitionParams) -> str:
    """HRP の d パラメータを生成し、明示 domain_id の特例を維持する

    Args:
        params (RecognitionParams): 解決済み認識設定

    Returns:
        str: URL エンコード済みの各値を含むドメイン指定
    """
    values = recognition_wire_values(params)
    parts = []
    if params.domain_id is not None:
        parts.append(params.domain_id)
        values = {wire: values[wire] for wire in ("confidenceLevel", "audioFilterProperties") if wire in values}
    parts.extend(f"{wire}={quote(value, encoding='UTF-8')}" for wire, value in values.items())
    return " ".join(part for part in parts if part)


@dataclass(frozen=True)
class HrpRequest:
    """HTTP 通信層へ渡す multipart 本文とヘッダー"""

    headers: dict[str, str]
    body: bytes


def build_hrp_request(params: RecognitionParams, api_key: str, audio: bytes, *, boundary: str | None = None) -> HrpRequest:
    """HRP multipart を生成する（音声のバイト列は変換しない）

    Args:
        params (RecognitionParams): 解決済み認識設定
        api_key (str): API 認証キー
        audio (bytes): 音声本文
        boundary (str | None): テスト用 MIME 境界、省略時はランダム

    Returns:
        HrpRequest: HTTP リクエストの本文とヘッダー
    """
    boundary = boundary or uuid.uuid4().hex
    values = {
        "d": build_hrp_domain(params),
        "c": params.codec,
        "r": params.result_type,
        "e": params.result_encoding,
        "u": api_key,
        "v": params.voice_detection,
    }
    parts = []
    for name, value in values.items():
        if value is not None and (value or name == "v"):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="a"\r\n\r\n'.encode())
    parts.extend((audio, f"\r\n--{boundary}--\r\n".encode()))
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "amivoice-api-client/0.1.0"}
    return HrpRequest(headers, b"".join(parts))


def _quote_wrp_value(value: str) -> str:
    """WRP の空白と二重引用符をエスケープする"""
    if " " in value or '"' in value:
        return '"' + value.replace('"', '""') + '"'
    return value


def build_wrp_start_command(params: RecognitionParams, api_key: str) -> str:
    """WRP 開始コマンドを直接生成する

    Args:
        params (RecognitionParams): 解決済み認識設定
        api_key (str): API 認証キー

    Returns:
        str: WebSocket のテキストメッセージとして送る開始コマンド
    """
    grammar = params.grammar_file_names or "\x01"
    if "\x01" in grammar and not grammar.endswith("\x01"):
        grammar += "\x01"
    values = recognition_wire_values(params)
    values.pop("grammarFileNames", None)
    values.pop("audioFilterProperties", None)
    if params.voice_detection is not None and params.segmenter_type is None:
        voice = params.voice_detection
        values["segmenterType"] = "G4"
        if len(voice) > 3 and voice[0] == "G" and voice[2] == " ":
            values["segmenterType"], voice = voice[:2], voice[3:]
        if params.segmenter_properties is None:
            values["segmenterProperties"] = voice
    if params.no_input_timeout is not None:
        values["noInputTimeout"] = str(params.no_input_timeout)
    values["authorization"] = api_key
    if params.result_type is not None:
        values["resultType"] = params.result_type
    options = "".join(f" {wire}={_quote_wrp_value(value)}" for wire, value in values.items())
    return f"s {params.codec or '16K'} {grammar}{options}"


@dataclass(frozen=True)
class WrpMessage:
    """確認応答とイベントを区別する WRP 解析結果"""

    command: str
    event: StreamEvent | None = None


def parse_wrp_message(message: str) -> WrpMessage:  # noqa: PLR0911
    """WRP 応答を制御情報または公開 StreamEvent へ変換する

    Args:
        message (str): 受信した UTF-8 テキストメッセージ

    Returns:
        WrpMessage: 制御コマンドと任意のイベント

    Raises:
        RecognitionError: サーバーエラーまたは不正な応答
    """
    if not message:
        return WrpMessage("")
    command, payload = message[0], message[2:]
    if command in {"s", "p", "e"}:
        if len(message) > 1:
            raise RecognitionError(f"WRP command rejected ({command}): {payload}")
        return WrpMessage(command)
    if command == "C":
        return WrpMessage(command)
    if len(message) < 2 or message[1] != " ":
        raise RecognitionError("Invalid WRP message: missing payload separator")
    if command in {"S", "E"}:
        try:
            time = int(payload)
        except ValueError as exc:
            raise RecognitionError("Invalid WRP utterance time") from exc
        event_type = "utterance_started" if command == "S" else "utterance_ended"
        return WrpMessage(
            command, StreamEvent(type=event_type, utterance=UtteranceEvent("started" if command == "S" else "ended", time))
        )
    if command == "U":
        return WrpMessage(command, StreamEvent(type="partial", text=payload))
    if command in {"A", "R"}:
        raw = "\x01" * 5 + payload if command == "R" else payload
        result = parse_result(raw, raise_on_error=False)
        return WrpMessage(command, StreamEvent(type="final", text=result.text, result=result))
    if command in {"Q", "G"}:
        return WrpMessage(command, StreamEvent(type="notification", notification=NotificationEvent(command, payload)))
    raise RecognitionError(f"Invalid WRP command: {command}")
