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
    {"code": "", "error_code": "INTERNAL_SERVER_ERROR", "error_message": "before processing sentiment-analyzer"},
    {"code": None, "error_code": "INTERNAL_SERVER_ERROR", "error_message": "before processing sentiment-analyzer"},
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
    expected_code = sentiment.get("code") if isinstance(sentiment.get("code"), int) else None
    assert result.code == expected_code and result.segments == ()
    assert result.parse_error is None
    assert result.data == sentiment and json.loads(result.raw) == sentiment


@pytest.mark.parametrize("sentiment", [{"segments": [sentiment_segment()]}, *ERRORS, {}])
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
        {"segments": [{"starttime": 0, "endtime": 100, "energy": None}]},
        {"code": True},
        {"code": "400"},
        {"code": None},
        {"code": ""},
        {"error_code": None},
        {"error_code": 400},
        {"error_message": []},
    ],
)
@pytest.mark.parametrize("envelope", ["flat", "compatible", "compatible-both", "outer", "inner"])
def test_wait_sentiment_shape_invalid_return_recognition_and_parse_error(sentiment: object, envelope: str) -> None:
    """不正な感情構造は元の値と解析エラーを保持して認識結果を返す"""
    # Given: 型破損した感情項目を含む正常認識
    data = job_with_sentiment(sentiment, envelope)
    before = deepcopy(data)
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([data]))
    # When: raise_on_error=Trueでも感情の解析失敗を分離する
    snapshot = client.wait("job1", raise_on_error=True)
    result = snapshot.recognition.sentiment_analysis
    # Then: 欠落や正常空と区別し、元データを改変しない
    assert snapshot.recognition.text == "認識"
    assert not snapshot.is_error and not snapshot.recognition.is_error
    assert result.is_error and result.parse_error
    assert result.segments == ()
    assert result.code is None and result.error_code is None and result.error_message is None
    assert result.data == sentiment and json.loads(result.raw) == sentiment
    assert snapshot.data == before and data == before
    assert json.loads(snapshot.raw) == before


@pytest.mark.parametrize("key", ["starttime", "endtime"])
@pytest.mark.parametrize("value", [None, True, "100", [], 10**1000])
def test_parse_job_sentiment_time_invalid_return_recognition_and_parse_error(key: str, value: object) -> None:
    """不正な区間時刻や数値オーバーフローを感情部分の解析失敗に限定する"""
    # Given: 不正な時刻
    sentiment = {"segments": [{**sentiment_segment(), key: value}]}
    # When: 完了応答を解析する
    snapshot = parse_job(json.dumps(job_with_sentiment(sentiment)).encode(), "job1")
    # Then: 不正時刻を補完せず、認識を保持する
    result = snapshot.recognition.sentiment_analysis
    assert snapshot.recognition.text == "認識" and not snapshot.is_error
    assert result.is_error and result.parse_error and result.segments == ()
    assert result.data == sentiment


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_parse_job_sentiment_non_json_number_invalid_raise_AsyncHttpApiError(value: float) -> None:
    """感情部分でもJSON自体に不正な非有限リテラルがあれば応答を拒否する"""
    # Given: JSON仕様外の数値を含む本文
    segment = {**sentiment_segment(), "starttime": value}
    raw = json.dumps(job_with_sentiment({"segments": [segment]})).encode()
    # When / Then: 応答全体のJSON検証は緩めない
    with pytest.raises(AsyncHttpApiError) as caught:
        parse_job(raw, "job1")
    assert caught.value.raw_body == raw


@pytest.mark.parametrize("key", ["starttime", "endtime"])
def test_parse_job_sentiment_missing_time_invalid_return_parse_error(key: str) -> None:
    """必須時刻の欠落を0で補完せず感情部分だけ解析エラーにする"""
    # Given: 時刻の片側が欠けた区間
    segment = sentiment_segment()
    del segment[key]
    # When: 完了応答を解析する
    snapshot = parse_job(json.dumps(job_with_sentiment({"segments": [segment]})).encode(), "job1")
    # Then: 認識結果は利用できる
    assert snapshot.recognition.text == "認識" and not snapshot.is_error
    assert snapshot.recognition.sentiment_analysis.is_error
    assert snapshot.recognition.sentiment_analysis.parse_error


@pytest.mark.parametrize("key", PARAMETERS)
@pytest.mark.parametrize("value", [True, 1.0, "1", None, []])
def test_parse_job_sentiment_known_parameter_invalid_return_parse_error(key: str, value: object) -> None:
    """既知の指標の非整数値を正常値として扱わず認識結果を保持する"""
    # Given: 値だけを破損させた区間
    sentiment = {"segments": [{**sentiment_segment(), key: value}]}
    # When: 完了応答を解析する
    snapshot = parse_job(json.dumps(job_with_sentiment(sentiment)).encode(), "job1")
    # Then: 感情部分だけエラーとして元データを保持する
    result = snapshot.recognition.sentiment_analysis
    assert snapshot.recognition.text == "認識" and not snapshot.is_error
    assert result.is_error and result.parse_error and result.segments == ()
    assert result.data == sentiment and json.loads(result.raw) == sentiment


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


@pytest.mark.parametrize("code", ["", None])
def test_parse_job_sentiment_empty_code_valid_return_normalized_code(code: str | None) -> None:
    """空文字とnullの感情コードを正規化し元データでは区別を保持する"""
    # Given: 正常空配列と空のコード
    sentiment = {"code": code, "segments": []}
    # When: 完了応答を解析する
    result = parse_job(json.dumps(job_with_sentiment(sentiment)).encode(), "job1").recognition.sentiment_analysis
    # Then: 型付きコードはNoneだが元の値は失わない
    assert result.code is None and result.parse_error is None and not result.is_error
    assert result.data == sentiment and json.loads(result.raw) == sentiment


def test_parse_job_sentiment_zero_code_valid_keep_existing_error_contract() -> None:
    """整数コード0の成否判定は指摘1の修正で変更しない"""
    # Given / When: 整数コード0と空配列を解析する
    result = parse_job(json.dumps(job_with_sentiment({"code": 0, "segments": []})).encode(), "job1")
    # Then: 整数コードがある場合の従来判定を維持する
    assert result.recognition.sentiment_analysis.code == 0
    assert result.recognition.sentiment_analysis.is_error
    assert result.recognition.sentiment_analysis.parse_error is None
    assert not result.is_error


def test_parse_job_sentiment_partial_invalid_discard_typed_segments_only() -> None:
    """途中まで正常な感情区間も解析成功とはせず元データに保持する"""
    # Given: 正常区間の後に型破損した区間がある
    sentiment = {"segments": [sentiment_segment(), {**sentiment_segment(), "energy": None}]}
    # When: 完了応答を解析する
    snapshot = parse_job(json.dumps(job_with_sentiment(sentiment)).encode(), "job1")
    # Then: 部分結果を成功と誤認させず全区間の元データを保持する
    result = snapshot.recognition.sentiment_analysis
    assert snapshot.recognition.text == "認識" and not snapshot.is_error
    assert result.is_error and result.parse_error and result.segments == ()
    assert result.data == sentiment and json.loads(result.raw) == sentiment


def test_parse_job_recognition_invalid_with_sentiment_parse_error_raise_AsyncHttpApiError() -> None:
    """感情のフォールバックで認識本体の型破損まで許容しない"""
    # Given: 認識テキストと感情結果の両方が不正
    data = job_with_sentiment({})
    data["text"] = None
    raw = json.dumps(data).encode()
    # When / Then: 認識本体の検証は従来どおりAPIエラーにする
    with pytest.raises(AsyncHttpApiError) as caught:
        parse_job(raw, "job1")
    assert caught.value.raw_body == raw


def test_parse_job_sentiment_double_envelope_invalid_raise_AsyncHttpApiError() -> None:
    """旧形式で感情結果の内外二重配置を拒否する"""
    # Given: 内側の感情結果と同じ値を外側にも置いた応答
    data = job_with_sentiment({"segments": []}, "inner")
    data["sentiment_analysis"] = {"segments": []}
    # When / Then: 片側を黙って捨てない
    with pytest.raises(AsyncHttpApiError):
        parse_job(json.dumps(data).encode(), "job1")
