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
        {"status": "future", "session_id": "job1"},
        {"status": "queued", "session_id": "wrong"},
        {"status": "error", "session_id": "job1"},
        {"status": "completed", "session_id": "job1"},
        {"status": "queued", "session_id": "job1", "audio_size": True},
        [],
    ],
)
def test_parse_job_malformed_invalid_raise_AsyncHttpApiError(data: object) -> None:
    """未知状態と壊れた応答を正常状態に変換しない"""
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
