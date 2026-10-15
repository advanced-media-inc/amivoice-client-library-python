"""公式に記載された非同期HTTPの応答構造を検証する"""

import json

import pytest

from amivoice._async_models import parse_job, parse_submission
from amivoice.exceptions import AsyncHttpApiError


@pytest.fixture
def recognition() -> dict[str, object]:
    """公式の発話区間構造に沿った合成データを返す"""
    return {
        "code": "",
        "message": "",
        "text": "テスト",
        "utteranceid": "utterance",
        "segments": [{"text": "テスト", "results": [{"text": "テスト", "tokens": [{"written": "テスト"}]}]}],
    }


def test_parse_submission_sessionid_valid_return_job_id() -> None:
    """受付応答のsessionidを正規化する"""
    # Given: 公式の受付成功形式
    raw = b'{"sessionid":"job1","text":"..."}'
    # When: 受付を解析する
    job = parse_submission(raw)
    # Then: ジョブIDと元データを保持する
    assert job.session_id == "job1"
    assert job.data == {"sessionid": "job1", "text": "..."}


@pytest.mark.parametrize("status", ["queued", "started", "processing", "error"])
def test_parse_job_intermediate_valid_return_snapshot(status: str) -> None:
    """処理中と失敗には認識結果がなくてもよい"""
    # Given: 各状態の応答
    data = {"status": status, "session_id": "job1"}
    if status == "error":
        data["error_message"] = "recognition failed"
    # When: 状態を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: 状態の終端と成否を区別する
    assert snapshot.recognition is None
    assert snapshot.is_terminal == (status == "error")
    assert snapshot.is_error == (status == "error")


@pytest.mark.parametrize("wrapped", [False, True])
def test_parse_job_segments_valid_return_typed_results(recognition: dict[str, object], wrapped: bool) -> None:
    """公式資料の平坦形式とresultsオブジェクト形式を扱う"""
    # Given: 公式資料で示された2種類の配置
    data = {"status": "completed", "session_id": "job1"}
    data.update({"results": recognition} if wrapped else recognition)
    # When: 完了結果を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: 区間と単語を失わない
    assert snapshot.recognition.text == "テスト"
    assert snapshot.recognition.segments[0].results[0].tokens[0].written == "テスト"
    assert snapshot.recognition.results[0].text == "テスト"
    assert not snapshot.is_error
    assert snapshot.data == data


def test_parse_job_compatible_valid_return_aggregated_results(recognition: dict[str, object]) -> None:
    """同期互換のresults配列を解析する"""
    # Given: segmentsではなく同期形式のresults
    data = {"status": "completed", "session_id": "job1", **recognition}
    data["results"] = data.pop("segments")[0]["results"]
    # When: 互換形式を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: 元の集約結果とテキストを得る
    assert snapshot.recognition.results[0].tokens[0].written == "テスト"
    assert snapshot.recognition.segments == ()


@pytest.mark.parametrize(
    "data",
    [
        {"status": "", "session_id": "job1"},
        {"status": "queued", "session_id": "wrong"},
        {"status": "error", "session_id": "job1"},
        {"status": "completed", "session_id": "job1"},
        {"status": "queued", "session_id": "job1", "audio_size": True},
        [],
    ],
)
def test_parse_job_malformed_invalid_raise_AsyncHttpApiError(data: object) -> None:
    """壊れた必須情報を正常状態に変換しない"""
    # Given: 不正なJSON応答
    body = json.dumps(data).encode()
    # When / Then: 不正応答は詳細付きの例外
    with pytest.raises(AsyncHttpApiError) as caught:
        parse_job(body, "job1")
    assert caught.value.raw_body == body


def test_parse_job_rejected_valid_return_error(recognition: dict[str, object]) -> None:
    """completedでも認識拒否は成功ではない"""
    # Given: 完了した認識エラー
    data = {"status": "completed", "session_id": "job1", **recognition, "code": "o", "message": "rejected", "text": ""}
    # When: 認識の成否を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: ジョブ完了とは別に認識失敗を返す
    assert snapshot.is_terminal and snapshot.is_error


@pytest.mark.parametrize("layout", ["flat", "wrapped", "compatible"])
@pytest.mark.parametrize("labels", [["speaker0", "speaker1", "speaker3", None], [None, None], []])
def test_parse_job_labels_valid_return_unmodified_tokens(layout: str, labels: list[str | None]) -> None:
    """全応答形式で欠番・欠落・無音を補完せず保持する"""
    # Given: 公式形式の単語ラベルと将来追加されるフィールド
    tokens = [
        {
            "written": f"単語{index}",
            "starttime": index * 100,
            "endtime": (index + 1) * 100,
            "future_token": {"value": index},
            **({"label": label} if label is not None else {}),
        }
        for index, label in enumerate(labels)
    ]
    utterances = [{"text": "認識", "tokens": tokens}]
    segment = {"text": "認識", "results": utterances, "future_segment": True}
    payload = {"text": "認識" if labels else "", "code": "", "message": "", "future_result": {"retained": True}}
    payload.update({"results": utterances} if layout == "compatible" else {"segments": [segment]})
    data = {
        "status": "completed",
        "session_id": "job1",
        "future_job": [1],
        **({"results": payload} if layout == "wrapped" else payload),
    }
    body = json.dumps(data, ensure_ascii=False).encode()
    # When: 取得応答を解析する
    snapshot = parse_job(body, "job1")
    result = snapshot.recognition
    parsed_tokens = result.results[0].tokens
    # Then: raw・dataとlabelを改変せず、segmentsとflatten結果も一致する
    assert [token.label for token in parsed_tokens] == labels
    assert [token.starttime for token in parsed_tokens] == [index * 100 for index in range(len(labels))]
    assert snapshot.raw == body.decode() and snapshot.data == data
    assert json.loads(result.raw) == result.data == (payload if layout == "wrapped" else data)
    if layout != "compatible":
        nested_tokens = result.segments[0].results[0].tokens
        assert [token.label for token in nested_tokens] == labels
        assert nested_tokens == parsed_tokens
        assert result.segments[0].data == segment
    else:
        assert result.segments == ()


def test_parse_job_same_label_valid_return_independent_requests() -> None:
    """同じspeaker0でも別リクエストの結果を名寄せしない"""
    # Given: 同一ラベルを持つ別リクエストの結果
    payload = {
        "status": "completed",
        "text": "認識",
        "code": "",
        "message": "",
        "results": [{"text": "認識", "tokens": [{"written": "認識", "label": "speaker0"}]}],
    }
    # When: リクエストを独立に解析する
    first = parse_job(json.dumps({**payload, "session_id": "job1"}).encode(), "job1")
    second = parse_job(json.dumps({**payload, "session_id": "job2"}).encode(), "job2")
    # Then: IDも結果も独立して保持される
    assert first.recognition.session_id == "job1" and second.recognition.session_id == "job2"
    assert first.recognition is not second.recognition
    assert first.recognition.results[0].tokens[0] is not second.recognition.results[0].tokens[0]
    assert first.recognition.results[0].tokens[0].label == second.recognition.results[0].tokens[0].label == "speaker0"
