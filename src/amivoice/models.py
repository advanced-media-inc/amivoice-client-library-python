"""AmiVoice 音声認識レスポンスのデータモデル。"""

import json
from dataclasses import dataclass
from typing import Literal

from .exceptions import RecognitionError

__all__ = [
    "NotificationEvent",
    "RecognitionResult",
    "StreamEvent",
    "StreamEventType",
    "UtteranceEvent",
]

StreamEventType = Literal["partial", "final", "utterance_started", "utterance_ended", "notification"]
"""``StreamEvent.type`` が取り得る値。

- ``"partial"``: 途中認識結果（``text`` に途中テキスト）。
- ``"final"``: 確定認識結果（``result`` に ``RecognitionResult``、``text`` に確定テキスト）。
- ``"utterance_started"`` / ``"utterance_ended"``: 発話境界（``utterance`` に ``UtteranceEvent``）。
- ``"notification"``: サービス通知（``notification`` に ``NotificationEvent``）。
"""


_R_COMMAND_PREFIX = "\x01\x01\x01\x01\x01"


@dataclass(frozen=True)
class RecognitionResult:
    """AmiVoice クライアントが返す正規化された認識結果。"""

    raw: str
    data: dict[str, object]
    is_error: bool = False
    session_id: str | None = None

    @property
    def text(self) -> str:
        """認識テキスト：``data["text"]`` のショートカット。

        ``data`` に ``"text"`` キーが存在しない場合は空文字列を返す。
        """
        val = self.data.get("text")
        return str(val) if val is not None else ""


@dataclass(frozen=True)
class UtteranceEvent:
    """WebSocket クライアントが発行する発話境界イベント。"""

    type: str
    time: int


@dataclass(frozen=True)
class NotificationEvent:
    """WebSocket クライアントが発行するサービス通知イベント。"""

    event_id: str
    event_message: str


@dataclass(frozen=True)
class StreamEvent:
    """``StreamSession.poll()`` / ``events()`` が返すストリーミング認識イベント。

    ``type`` によってどのフィールドが有効かが決まる（:data:`StreamEventType` を参照）。

    - ``type == "partial"``: ``text`` に途中認識テキスト。
    - ``type == "final"``: ``result`` に確定認識結果、``text`` に確定テキスト。
    - ``type == "utterance_started"`` / ``"utterance_ended"``: ``utterance`` に発話境界イベント。
    - ``type == "notification"``: ``notification`` にサービス通知イベント。
    """

    type: StreamEventType
    text: str = ""
    result: RecognitionResult | None = None
    utterance: UtteranceEvent | None = None
    notification: NotificationEvent | None = None

    @property
    def is_final(self) -> bool:
        """確定認識結果イベント（``type == "final"``）か否か。"""
        return self.type == "final"

    @property
    def is_partial(self) -> bool:
        """途中認識結果イベント（``type == "partial"``）か否か。"""
        return self.type == "partial"


def parse_result(raw: str, raise_on_error: bool = True) -> RecognitionResult:
    """AmiVoice の生レスポンスを ``RecognitionResult`` に変換する。

    Args:
        raw: Hrp/Wrp ライブラリが返す生のレスポンステキスト。
        raise_on_error: エラー結果の場合に ``RecognitionError`` を送出するか否か。

    Returns:
        RecognitionResult型に変換された認識結果。

    Raises:
        RecognitionError: JSON のパースに失敗した場合、JSON オブジェクト以外の場合、
            または ``raise_on_error`` が ``True`` のときにエラー結果であった場合。
    """
    is_error = raw.startswith(_R_COMMAND_PREFIX)
    parsed_raw = raw[len(_R_COMMAND_PREFIX) :] if is_error else raw
    try:
        parsed_json = json.loads(parsed_raw)
    except json.JSONDecodeError as exc:
        raise RecognitionError(str(exc)) from exc
    if not isinstance(parsed_json, dict):
        raise RecognitionError("Recognition result must be a JSON object")
    data: dict[str, object] = {str(k): v for k, v in parsed_json.items()}
    # code="" は成功、code="o" はフィラーのみ認識の可能性があるので成功扱い、それ以外はエラー
    if not is_error:
        code = data.get("code")
        if isinstance(code, str) and code not in ("", "o"):
            is_error = True
    result = RecognitionResult(raw=parsed_raw, data=data, is_error=is_error)
    if is_error and raise_on_error:
        message_val = data.get("message")
        message = str(message_val if message_val is not None else (data.get("code") or data))
        raise RecognitionError(message, result=result)
    return result
