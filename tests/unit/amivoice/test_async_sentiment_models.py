"""感情結果の型付き解析、エラー分離、非破壊と前方互換性を検証する"""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields
from typing import get_type_hints

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncHttpApiError, AsyncJobError, AsyncRecognitionResult
from amivoice._async_models import parse_job

from .test_async_client import RecordingTransport, completed, queued

PARAMETERS = (
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
)
ERRORS = [
    {"code": 400, "error_code": "BAD_REQUEST", "error_message": "file format is invalid"},
    {"code": 500, "error_code": "INTERNAL_SERVER_ERROR", "error_message": "internal server error has occurred"},
    {"error_code": "INTERNAL_SERVER_ERROR", "error_message": "before processing sentiment-analyzer"},
]


def sentiment_segment() -> dict[str, object]:
    """公式キーを使った匿名合成区間を返す"""
    return {"starttime": 10, "endtime": 2000, **dict.fromkeys(PARAMETERS, 0), "emo_cog": 1, "atmosphere": -100}


def job_with_sentiment(sentiment: object, envelope: str = "flat") -> dict[str, object]:
    """現在形式・互換形式・旧形式の合成完了応答を返す"""
    data = completed()
    if envelope in ("compatible", "compatible-both"):
        data["results"] = data["segments"][0]["results"]
        if envelope == "compatible":
            data.pop("segments")
    if envelope in ("outer", "inner"):
        payload = {key: data.pop(key) for key in ("code", "message", "text", "segments")}
        data["results"] = payload
        target = payload if envelope == "inner" else data
    else:
        target = data
    target["sentiment_analysis"] = sentiment
    return data


@pytest.mark.parametrize("envelope", ["flat", "compatible", "compatible-both", "outer", "inner"])
def test_parse_job_sentiment_envelope_valid_return_non_destructive_result(envelope: str) -> None:
    """認識と感情の両区間および各階層の元データを失わない"""
    # Given: 20指標・未知の整数・未知メタデータを含む結果
    segment = {**sentiment_segment(), "future_parameter": -5, "extra": {"info": "future"}}
    sentiment = {"segments": [segment, {**segment, "starttime": 1500.5, "endtime": 3000.25}], "extra": True}
    data = job_with_sentiment(sentiment, envelope)
    before = deepcopy(data)
    raw = json.dumps(data, ensure_ascii=False)
    # When: 完了応答を解析する
    snapshot = parse_job(raw.encode(), "job1")
    result = snapshot.recognition.sentiment_analysis
    # Then: 入力原文と辞書を保持し整数値は未知キーもそのまま返す
    assert snapshot.raw == raw and snapshot.data == before and data == before
    assert result.data == sentiment and json.loads(result.raw) == sentiment
    assert not result.is_error and not snapshot.is_error
    assert snapshot.recognition.text == "認識"
    assert len(result.segments) == 2
    assert result.segments[0].data == segment and json.loads(result.segments[0].raw) == segment
    assert result.segments[0].parameters == {
        key: value for key, value in segment.items() if key not in ("starttime", "endtime", "extra")
    }
    assert result.segments[1].starttime == 1500.5 and result.segments[1].endtime == 3000.25
    assert "extra" not in result.segments[0].parameters
    payload = before["results"] if envelope in ("outer", "inner") else before
    assert snapshot.recognition.data == payload and json.loads(snapshot.recognition.raw) == payload
    assert all(not hasattr(part, "sentiment_analysis") for part in snapshot.recognition.segments)


@pytest.mark.parametrize("parameter", PARAMETERS)
def test_segment_parameter_property_valid_return_current_dictionary_value(parameter: str) -> None:
    """既知20指標は読み取り専用の明示プロパティで二重保持しない"""
    # Given: 型付き解析した区間
    snapshot = parse_job(json.dumps(job_with_sentiment({"segments": [sentiment_segment()]})).encode(), "job1")
    segment = snapshot.recognition.sentiment_analysis.segments[0]
    # When / Then: 補完・静的型チェック可能で0や負数も保持する
    prop = getattr(type(segment), parameter)
    assert isinstance(prop, property) and prop.fset is None
    assert get_type_hints(prop.fget)["return"] == int | None
    assert getattr(segment, parameter) == segment.parameters[parameter]
    assert not set(PARAMETERS) & {field.name for field in fields(segment)}
    with pytest.raises(FrozenInstanceError):
        setattr(segment, parameter, 5)
    segment.parameters[parameter] = -10
    assert getattr(segment, parameter) == -10
    del segment.parameters[parameter]
    assert getattr(segment, parameter) is None


@pytest.mark.parametrize("envelope", ["flat", "compatible", "outer", "inner"])
@pytest.mark.parametrize("sentiment", [*ERRORS, {"segments": []}, {"code": 0}, {"error_message": "failed"}])
def test_wait_sentiment_only_valid_return_recognition_without_raising(envelope: str, sentiment: dict[str, object]) -> None:
    """感情分析内のエラーを音声認識の成否やwaitの例外へ波及させない"""
    # Given: 正常認識に感情結果を添えた応答
    data = job_with_sentiment(sentiment, envelope)
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([data]))
    # When: raise_on_error=Trueで回収する
    snapshot = client.wait("job1", raise_on_error=True)
    result = snapshot.recognition.sentiment_analysis
    # Then: 感情だけが失敗しても認識テキストを回収できる
    assert snapshot.recognition.text == "認識"
    assert not snapshot.is_error and not snapshot.recognition.is_error
    assert result.is_error == ("segments" not in sentiment)
    assert result.code == sentiment.get("code") and result.segments == ()


@pytest.mark.parametrize("sentiment", [{"segments": [sentiment_segment()]}, *ERRORS])
@pytest.mark.parametrize("raise_on_error", [False, True])
def test_wait_recognition_error_valid_return_or_raise_with_sentiment(sentiment: dict[str, object], raise_on_error: bool) -> None:
    """認識が失敗したcompletedでも感情結果を保持し既存例外契約を維持する"""
    # Given: 認識だけ失敗した完了結果
    data = job_with_sentiment(sentiment)
    data.update(code="o", message="rejected", text="", segments=[])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([data]))
    # When: 完了結果を回収する
    if raise_on_error:
        with pytest.raises(AsyncJobError) as caught:
            client.wait("job1")
        snapshot = caught.value.snapshot
    else:
        snapshot = client.wait("job1", raise_on_error=False)
    # Then: 認識側と感情側の失敗を別々に参照できる
    assert snapshot.is_error and snapshot.recognition.is_error
    assert snapshot.recognition.sentiment_analysis.data == sentiment
    assert snapshot.recognition.sentiment_analysis.is_error == ("segments" not in sentiment)


@pytest.mark.parametrize("status", ["queued", "started", "processing", "error"])
def test_parse_job_non_completed_sentiment_invalid_return_no_recognition(status: str) -> None:
    """非completedの感情項目は認識モデルを生成せず解析しない"""
    # Given: 解析対象外の状態に不正な感情項目がある
    data = {**queued(status), "sentiment_analysis": None}
    if status == "error":
        data["error_message"] = "failed"
    # When: 状態を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: 非completedの既存契約を維持する
    assert snapshot.recognition is None


def test_parse_job_missing_sentiment_valid_return_none_and_positional_compatibility() -> None:
    """未返却はNoneで既存モデルの位置引数も維持する"""
    # Given: 感情項目のない正常結果
    data = completed()
    # When: 解析し既存の位置引数でモデルを生成する
    result = parse_job(json.dumps(data).encode(), "job1").recognition
    positional = AsyncRecognitionResult(
        result.raw, result.data, result.is_error, result.session_id, result.results, result.segments
    )
    # Then: 新項目はキーワード専用でデフォルトNone
    assert result.sentiment_analysis is None and positional == result


@pytest.mark.parametrize(
    "sentiment",
    [
        None,
        [],
        "result",
        1,
        {},
        {"segments": None},
        {"segments": {}},
        {"segments": [1]},
        {"code": True},
        {"code": "400"},
        {"code": None},
        {"error_code": None},
        {"error_code": 400},
        {"error_message": []},
    ],
)
def test_parse_job_sentiment_shape_invalid_raise_AsyncHttpApiError(sentiment: object) -> None:
    """不正な構造やエラー項目の型を正常空へ変換しない"""
    # Given: 型破損した感情項目
    raw = json.dumps(job_with_sentiment(sentiment)).encode()
    # When / Then: 元応答を持つ既存APIエラーへ変換する
    with pytest.raises(AsyncHttpApiError) as caught:
        parse_job(raw, "job1")
    assert caught.value.raw_body == raw


@pytest.mark.parametrize("key", ["starttime", "endtime"])
@pytest.mark.parametrize("value", [None, True, "100", [], float("nan"), float("inf"), 10**1000])
def test_parse_job_sentiment_time_invalid_raise_AsyncHttpApiError(key: str, value: object) -> None:
    """区間時刻はboolを除く有限の数値だけ許可する"""
    # Given: 不正な時刻
    segment = {**sentiment_segment(), key: value}
    # When / Then: 型破損をAPIエラーへ変換する
    with pytest.raises(AsyncHttpApiError):
        parse_job(json.dumps(job_with_sentiment({"segments": [segment]})).encode(), "job1")


@pytest.mark.parametrize("key", ["starttime", "endtime"])
def test_parse_job_sentiment_missing_time_invalid_raise_AsyncHttpApiError(key: str) -> None:
    """必須時刻の欠落を0で補完しない"""
    # Given: 時刻の片側が欠けた区間
    segment = sentiment_segment()
    del segment[key]
    # When / Then: 不正応答として拒否する
    with pytest.raises(AsyncHttpApiError):
        parse_job(json.dumps(job_with_sentiment({"segments": [segment]})).encode(), "job1")


@pytest.mark.parametrize("key", PARAMETERS)
@pytest.mark.parametrize("value", [True, 1.0, "1", None, []])
def test_parse_job_sentiment_known_parameter_invalid_raise_AsyncHttpApiError(key: str, value: object) -> None:
    """既知の指標は整数限定でnullやfloatも拒否する"""
    # Given: 値だけを破損させた区間
    segment = {**sentiment_segment(), key: value}
    # When / Then: 各指標の型を検証する
    with pytest.raises(AsyncHttpApiError):
        parse_job(json.dumps(job_with_sentiment({"segments": [segment]})).encode(), "job1")


def test_parse_job_sentiment_sparse_out_of_range_valid_return_without_clamp() -> None:
    """省略・範囲外・未知メタデータを固定数検査や範囲補正なしに扱う"""
    # Given: 既知指標の大半が省略された結果
    segment = {"starttime": 0.5, "endtime": 1, "energy": 1000, "future": 7, "metadata": True}
    # When: 区間を解析する
    result = parse_job(json.dumps(job_with_sentiment({"segments": [segment]})).encode(), "job1")
    typed = result.recognition.sentiment_analysis.segments[0]
    # Then: 定義APIへの通信なしで保持する
    assert typed.energy == 1000 and typed.stress is None
    assert typed.parameters == {"energy": 1000, "future": 7}
    assert typed.data["metadata"] is True


def test_get_job_sentiment_diarization_valid_return_separate_results() -> None:
    """話者トークンと感情区間を独立して保持し自動対応付けしない"""
    # Given: 両方の結果が同梱された正常応答
    data = job_with_sentiment({"segments": [sentiment_segment()]})
    data["segments"][0]["results"][0]["tokens"][0]["label"] = "speaker0"
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([data]))
    # When: 公開APIで回収する
    snapshot = client.get_job("job1")
    # Then: 認識側だけに話者ラベルを保持する
    assert snapshot.recognition.results[0].tokens[0].label == "speaker0"
    assert not hasattr(snapshot.recognition.sentiment_analysis.segments[0], "label")
    assert "label" not in snapshot.recognition.sentiment_analysis.segments[0].data


def test_parse_job_sentiment_double_envelope_invalid_raise_AsyncHttpApiError() -> None:
    """旧形式で感情結果の内外二重配置を拒否する"""
    # Given: 内側の感情結果と同じ値を外側にも置いた応答
    data = job_with_sentiment({"segments": []}, "inner")
    data["sentiment_analysis"] = {"segments": []}
    # When / Then: 片側を黙って捨てない
    with pytest.raises(AsyncHttpApiError):
        parse_job(json.dumps(data).encode(), "job1")
