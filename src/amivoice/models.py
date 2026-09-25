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
    "Token",
    "UtteranceEvent",
    "UtteranceResult",
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
class Token:
    """単語単位の認識結果。"""

    written: str
    spoken: str | None = None
    confidence: float | None = None
    starttime: int | None = None
    endtime: int | None = None
    label: str | None = None
    language: str | None = None


@dataclass(frozen=True)
class UtteranceResult:
    """発話区間の認識結果。"""

    text: str
    tokens: tuple[Token, ...] = ()
    confidence: float | None = None
    starttime: int | None = None
    endtime: int | None = None
    tags: tuple[str, ...] = ()
    rulename: str | None = None


@dataclass(frozen=True)
class RecognitionResult:
    """AmiVoice クライアントが返す正規化された認識結果。"""

    raw: str
    data: dict[str, object]
    is_error: bool = False
    session_id: str | None = None
    results: tuple[UtteranceResult, ...] = ()

    @property
    def text(self) -> str:
        """認識テキスト：``data["text"]`` のショートカット。

        ``data`` に ``"text"`` キーが存在しない場合は空文字列を返す。

        Returns:
            str: 認識テキスト。``data`` に ``"text"`` がない場合は空文字列
        """
        val = self.data.get("text")
        return str(val) if val is not None else ""

    @property
    def utterance_id(self) -> str | None:
        """発話 ID：``data["utteranceid"]`` のショートカット。

        Returns:
            str | None: 発話 ID。``data`` に ``"utteranceid"`` がない場合は ``None``
        """
        val = self.data.get("utteranceid")
        return str(val) if val is not None else None


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
        """確定認識結果イベント（``type == "final"``）か否か。

        Returns:
            bool: 確定認識結果イベントの場合は ``True``
        """
        return self.type == "final"

    @property
    def is_partial(self) -> bool:
        """途中認識結果イベント（``type == "partial"``）か否か。

        Returns:
            bool: 途中認識結果イベントの場合は ``True``
        """
        return self.type == "partial"


def _opt_str(value: object) -> str | None:
    """任意の文字列フィールドをパースする。

    Args:
        value: パース対象の値

    Returns:
        文字列または ``None``

    Raises:
        RecognitionError: 値が文字列でも ``None`` でもない場合
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecognitionError("Recognition result optional string field must be a string")
    return value


def _opt_float(value: object) -> float | None:
    """任意の数値フィールドを浮動小数点数へパースする。

    Args:
        value: パース対象の値

    Returns:
        浮動小数点数または ``None``

    Raises:
        RecognitionError: 値が数値でも ``None`` でもない場合、または bool の場合
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecognitionError("Recognition result optional float field must be a number")
    return float(value)


def _opt_int(value: object) -> int | None:
    """任意の数値フィールドを整数へパースする。

    Args:
        value: パース対象の値

    Returns:
        整数または ``None``

    Raises:
        RecognitionError: 値が数値でも ``None`` でもない場合、または bool の場合
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecognitionError("Recognition result optional integer field must be a number")
    return int(value)


def _parse_token(item: dict[str, object]) -> Token:
    """単語結果の JSON オブジェクトを ``Token`` へ変換する。

    Args:
        item: 単語結果の JSON オブジェクト

    Returns:
        型付きの単語結果

    Raises:
        RecognitionError: ``written`` が文字列でない場合、または任意フィールドの型が不正な場合
    """
    written = item.get("written")
    if not isinstance(written, str):
        raise RecognitionError("Recognition result token field 'written' must be a string")
    return Token(
        written=written,
        spoken=_opt_str(item.get("spoken")),
        confidence=_opt_float(item.get("confidence")),
        starttime=_opt_int(item.get("starttime")),
        endtime=_opt_int(item.get("endtime")),
        label=_opt_str(item.get("label")),
        language=_opt_str(item.get("language")),
    )


def _parse_utterance(item: dict[str, object]) -> UtteranceResult:
    """発話区間の JSON オブジェクトを ``UtteranceResult`` へ変換する。

    Args:
        item: 発話区間の JSON オブジェクト

    Returns:
        型付きの発話区間結果

    Raises:
        RecognitionError: 必須フィールドや任意フィールドの型が不正な場合
    """
    text = item.get("text")
    if not isinstance(text, str):
        raise RecognitionError("Recognition result utterance field 'text' must be a string")

    tokens_value = item.get("tokens", [])
    if not isinstance(tokens_value, list):
        raise RecognitionError("Recognition result utterance field 'tokens' must be an array")
    tokens: list[Token] = []
    for token_value in tokens_value:
        if not isinstance(token_value, dict):
            raise RecognitionError("Recognition result token must be a JSON object")
        tokens.append(_parse_token(token_value))

    tags_value = item.get("tags", [])
    if not isinstance(tags_value, list):
        raise RecognitionError("Recognition result utterance field 'tags' must be an array")
    tags: list[str] = []
    for tag_value in tags_value:
        if not isinstance(tag_value, str):
            raise RecognitionError("Recognition result utterance field 'tags' must contain strings")
        tags.append(tag_value)

    return UtteranceResult(
        text=text,
        tokens=tuple(tokens),
        confidence=_opt_float(item.get("confidence")),
        starttime=_opt_int(item.get("starttime")),
        endtime=_opt_int(item.get("endtime")),
        tags=tuple(tags),
        rulename=_opt_str(item.get("rulename")),
    )


def _parse_utterances(value: object) -> tuple[UtteranceResult, ...]:
    """認識結果の発話区間配列を型付きタプルへ変換する。

    Args:
        value: ``results`` フィールドの値

    Returns:
        型付き発話区間結果のタプル

    Raises:
        RecognitionError: ``results`` が配列でない場合、または要素の型が不正な場合
    """
    if not isinstance(value, list):
        raise RecognitionError("Recognition result field 'results' must be an array")

    utterances: list[UtteranceResult] = []
    for utterance_value in value:
        if not isinstance(utterance_value, dict):
            raise RecognitionError("Recognition result utterance must be a JSON object")
        utterances.append(_parse_utterance(utterance_value))
    return tuple(utterances)


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
    results = _parse_utterances(data.get("results", []))
    result = RecognitionResult(raw=parsed_raw, data=data, is_error=is_error, results=results)
    if is_error and raise_on_error:
        message_val = data.get("message")
        message = str(message_val if message_val is not None else (data.get("code") or data))
        raise RecognitionError(message, result=result)
    return result
