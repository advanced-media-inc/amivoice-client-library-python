"""公式の平坦・resultsオブジェクト・同期互換応答を明示的に解析する"""

import json
import math

from .async_models import AsyncJobSnapshot, AsyncJobSubmission, AsyncRecognitionResult, SentimentAnalysisResult, SentimentSegment
from .exceptions import AsyncHttpApiError, AsyncHttpAuthenticationError, RecognitionError
from .models import parse_result


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
    except (ValueError, TypeError, RecursionError):
        error = AsyncHttpApiError("Async HTTP job submission was rejected or invalid", status_code=200, raw_body=body)
        if error.code == "-":
            raise AsyncHttpAuthenticationError(error.message, status_code=200, raw_body=body) from None
        raise error from None


_SENTIMENT_PARAMETERS = frozenset(
    {
        "energy",
        "stress",
        "emo_cog",
        "concentration",
        "anticipation",
        "excitement",
        "hesitation",
        "uncertainty",
        "intensive_thinking",
        "imagination_activity",
        "embarrassment",
        "passionate",
        "brain_power",
        "confidence",
        "aggression",
        "atmosphere",
        "upset",
        "content",
        "dissatisfaction",
        "extreme_emotion",
    }
)


def _sentiment_segment(data: object) -> SentimentSegment:
    if not isinstance(data, dict):
        raise ValueError("Sentiment segment must be an object")
    for key in ("starttime", "endtime"):
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Sentiment times must be finite numbers")
    parameters = {}
    for key, value in data.items():
        if key in ("starttime", "endtime"):
            continue
        integer = isinstance(value, int) and not isinstance(value, bool)
        if key in _SENTIMENT_PARAMETERS and not integer:
            raise ValueError("Known sentiment parameters must be integers")
        if integer:
            parameters[key] = value
    return SentimentSegment(data["starttime"], data["endtime"], parameters, json.dumps(data, ensure_ascii=False), data)


def _parse_sentiment(data: object) -> SentimentAnalysisResult:
    if not isinstance(data, dict) or not any(key in data for key in ("segments", "code", "error_code", "error_message")):
        raise ValueError("Sentiment result requires segments or error fields")
    code = data.get("code")
    if code == "":
        code = None
    if code is not None and (isinstance(code, bool) or not isinstance(code, int)):
        raise ValueError("Sentiment code must be an integer")
    if code is None and not any(key in data for key in ("segments", "error_code", "error_message")):
        raise ValueError("Sentiment result requires segments or error fields")
    for key in ("error_code", "error_message"):
        if key in data and not isinstance(data[key], str):
            raise ValueError("Sentiment error fields must be strings")
    segments = ()
    if "segments" in data:
        if not isinstance(data["segments"], list):
            raise ValueError("Sentiment segments must be an array")
        segments = tuple(_sentiment_segment(segment) for segment in data["segments"])
    return SentimentAnalysisResult(
        raw=json.dumps(data, ensure_ascii=False),
        data=data,
        segments=segments,
        code=code,
        error_code=data.get("error_code"),
        error_message=data.get("error_message"),
    )


def _sentiment(data: object) -> SentimentAnalysisResult:
    # 付随する感情部分の型破損で正常な認識結果の取得を妨げない
    try:
        return _parse_sentiment(data)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return SentimentAnalysisResult(raw=json.dumps(data, ensure_ascii=False), data=data, parse_error=str(error))


def _recognition(data: dict[str, object], session_id: str) -> AsyncRecognitionResult:
    # マニュアルの旧オブジェクト形式と現在の平坦形式を区別する
    payload = data.get("results") if isinstance(data.get("results"), dict) else data
    if payload is not data and any(key in data for key in ("segments", "text", "code", "message")):
        raise ValueError("Ambiguous recognition envelope")
    for key in ("text", "code", "message"):
        if not isinstance(payload.get(key), str):
            raise ValueError("Completed result requires text, code and message")
    if payload is not data and "sentiment_analysis" in data and "sentiment_analysis" in payload:
        raise ValueError("Ambiguous sentiment envelope")
    sentiment_source = data if "sentiment_analysis" in data else payload
    sentiment = _sentiment(sentiment_source["sentiment_analysis"]) if "sentiment_analysis" in sentiment_source else None
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
    elif "results" in payload:
        if not isinstance(payload["results"], list):
            raise ValueError("Compatible results must be an array")
    elif not (payload["code"] or payload["message"]):
        raise ValueError("Successful result requires segments or compatible results")
    # parse_resultはresults配列用なので、ネストしたオブジェクトへ直接渡さない
    normalized = parse_result(raw, raise_on_error=False)
    is_error = normalized.is_error or any(segment.is_error for segment in segments)
    utterances = normalized.results or tuple(utterance for segment in segments for utterance in segment.results)
    return AsyncRecognitionResult(
        raw=raw,
        data=payload,
        is_error=is_error,
        session_id=session_id,
        results=utterances,
        segments=tuple(segments),
        sentiment_analysis=sentiment,
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
        if not isinstance(status, str) or not status or any(ord(char) <= 32 or ord(char) == 127 for char in status):
            raise ValueError("Job status must be a non-empty label without whitespace or control characters")
        size = data.get("audio_size")
        if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < 0):
            raise ValueError("audio_size must be a non-negative integer")
        error = _optional_string(data, "error_message")
        if status == "error" and not error:
            raise ValueError("Error status requires error_message")
        return AsyncJobSnapshot(
            session_id=session_id,
            status=status,
            raw=raw,
            data=data,
            service_id=_optional_string(data, "service_id"),
            content_id=_optional_string(data, "content_id"),
            audio_size=size,
            audio_md5=_optional_string(data, "audio_md5"),
            error_message=error,
            recognition=_recognition(data, session_id) if status == "completed" else None,
        )
    except (ValueError, TypeError, RecognitionError, OverflowError, RecursionError):
        raise AsyncHttpApiError(
            "Async HTTP returned an invalid job response", status_code=200, raw_body=body, session_id=session_id
        ) from None
