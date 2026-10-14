"""公式の平坦・resultsオブジェクト・同期互換応答を明示的に解析する"""

import json
from typing import cast

from .async_models import AsyncJobSnapshot, AsyncJobStatus, AsyncJobSubmission, AsyncRecognitionResult
from .exceptions import AsyncHttpApiError, AsyncHttpAuthenticationError, RecognitionError
from .models import parse_result

_STATUSES = frozenset({"queued", "started", "processing", "completed", "error"})


def _reject_constant(value: str) -> None:
    raise ValueError("JSON constants must be finite")


def _decode(body: bytes) -> tuple[str, dict[str, object]]:
    raw = body.decode("utf-8")
    data = json.loads(raw, parse_constant=_reject_constant)
    if not isinstance(data, dict):
        raise ValueError("Response must be a JSON object")
    return raw, data


def _optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError("Optional field must be a string")
    return value


def _session_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in (".", "..")
        or any(ord(c) <= 32 or ord(c) == 127 or c in "/\\" for c in value)
    ):
        raise ValueError("Missing or invalid job ID")
    return value


def parse_submission(body: bytes) -> AsyncJobSubmission:
    """HTTP200の受付応答をIDの有無とエラー情報で検証する

    Args:
        body (bytes): 受付のUTF-8 JSON

    Returns:
        AsyncJobSubmission: 正常に受理されたジョブ

    Raises:
        AsyncHttpApiError: 受付失敗又は不正なJSON
    """
    try:
        raw, data = _decode(body)
        for key in ("code", "message"):
            if _optional_string(data, key):
                raise ValueError("Job was rejected")
        return AsyncJobSubmission(_session_id(data.get("sessionid")), raw, data)
    except (ValueError, TypeError):
        error = AsyncHttpApiError("Async HTTP job submission was rejected or invalid", status_code=200, raw_body=body)
        if error.code == "-":
            raise AsyncHttpAuthenticationError(error.message, status_code=200, raw_body=body) from None
        raise error from None


def _recognition(data: dict[str, object], session_id: str) -> AsyncRecognitionResult:
    # マニュアルの旧オブジェクト形式と現在の平坦形式を区別する
    payload = data.get("results") if isinstance(data.get("results"), dict) else data
    if payload is not data and any(key in data for key in ("segments", "text", "code", "message")):
        raise ValueError("Ambiguous recognition envelope")
    for key in ("text", "code", "message"):
        if not isinstance(payload.get(key), str):
            raise ValueError("Completed result requires text, code and message")
    raw = json.dumps(payload, ensure_ascii=False)
    segments = []
    if "segments" in payload:
        if not isinstance(payload["segments"], list):
            raise ValueError("segments must be an array")
        for segment in payload["segments"]:
            if (
                not isinstance(segment, dict)
                or not isinstance(segment.get("text"), str)
                or not isinstance(segment.get("results"), list)
            ):
                raise ValueError("Segment requires text and results")
            segments.append(parse_result(json.dumps(segment, ensure_ascii=False), raise_on_error=False))
    elif not isinstance(payload.get("results"), list):
        raise ValueError("Completed result requires segments or compatible results")
    # parse_resultはresults配列用なので、ネストしたオブジェクトへ直接渡さない
    normalized = parse_result(raw, raise_on_error=False)
    is_error = normalized.is_error or any(segment.is_error for segment in segments)
    if not is_error and not normalized.text:
        raise ValueError("Successful recognition contains no text")
    utterances = normalized.results or tuple(utterance for segment in segments for utterance in segment.results)
    return AsyncRecognitionResult(
        raw=raw, data=payload, is_error=is_error, session_id=session_id, results=utterances, segments=tuple(segments)
    )


def parse_job(body: bytes, session_id: str) -> AsyncJobSnapshot:
    """取得応答を検証し、ジョブ状態と認識の成否を分けて返す

    Args:
        body (bytes): 状態取得のUTF-8 JSON
        session_id (str): 問い合わせたジョブID

    Returns:
        AsyncJobSnapshot: 観測したジョブ状態

    Raises:
        AsyncHttpApiError: 状態、ID、型、認識結果が不正な場合
    """
    try:
        raw, data = _decode(body)
        if _session_id(data.get("session_id")) != session_id:
            raise ValueError("Job ID mismatch")
        status = data.get("status")
        if not isinstance(status, str) or status not in _STATUSES:
            raise ValueError("Unknown job status")
        size = data.get("audio_size")
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
            raise ValueError("audio_size must be a non-negative integer")
        error = _optional_string(data, "error_message")
        if status == "error" and not error:
            raise ValueError("Error status requires error_message")
        return AsyncJobSnapshot(
            session_id=session_id,
            status=cast("AsyncJobStatus", status),
            raw=raw,
            data=data,
            service_id=_optional_string(data, "service_id"),
            content_id=_optional_string(data, "content_id"),
            audio_size=size,
            audio_md5=_optional_string(data, "audio_md5"),
            error_message=error,
            recognition=_recognition(data, session_id) if status == "completed" else None,
        )
    except (ValueError, TypeError, RecognitionError, OverflowError):
        raise AsyncHttpApiError(
            "Async HTTP returned an invalid job response", status_code=200, raw_body=body, session_id=session_id
        ) from None
