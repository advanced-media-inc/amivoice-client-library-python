"""応答の前方互換性と必須の安全性検証を確認する"""

import json

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncHttpApiError, AsyncJobTimeoutError
from amivoice._async_models import parse_job

from .test_async_client import RecordingTransport, completed
from .test_async_retry import fake_clock


def test_parse_job_unknown_status_valid_return_preserved_snapshot() -> None:
    """未知の状態と追加フィールドを失わず非終端として保持する"""
    # Given: 将来追加される状態と未知フィールド
    data = {"session_id": "job1", "status": "finalizing", "progress": {"percent": 95}, "text": "partial"}
    # When: 状態を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: 未知の状態を成功や終端へ変換しない
    assert snapshot.status == "finalizing" and snapshot.data == data
    assert not snapshot.is_terminal and not snapshot.is_error
    assert snapshot.recognition is None


@pytest.mark.parametrize("finish", [True, False])
def test_wait_unknown_status_edge_return_or_timeout(finish: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """未知の状態は待機を継続するが全体期限は守る"""
    # Given: 未知状態が返るジョブ
    responses = [{"session_id": "job1", "status": "finalizing"}]
    if finish:
        responses.append(completed())
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport(responses))
    fake_clock(client, monkeypatch)
    # When / Then: 既知の終端状態又はタイムアウトまで待つ
    if finish:
        assert client.wait("job1", poll_interval=1, timeout=2).status == "completed"
    else:
        with pytest.raises(AsyncJobTimeoutError) as caught:
            client.wait("job1", poll_interval=1, timeout=1)
        assert caught.value.snapshot.status == "finalizing"


@pytest.mark.parametrize("wrapped", [True, False])
@pytest.mark.parametrize("details", ["segments", "results"])
def test_parse_job_empty_text_valid_return_result(wrapped: bool, details: str) -> None:
    """空文字列の結果も型が正しければ本文を保持して返す"""
    # Given: 空の認識結果
    payload = {"text": "", "code": "", "message": "", details: [], "new_field": 1}
    data = {"session_id": "job1", "status": "completed", **({"results": payload} if wrapped else payload)}
    # When: 完了応答を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: エラーコードなしの空結果を不正JSONと混同しない
    assert snapshot.recognition.text == "" and snapshot.recognition.results == ()
    assert snapshot.recognition.data["new_field"] == 1
    assert snapshot.is_terminal and not snapshot.is_error


@pytest.mark.parametrize("wrapped", [True, False])
def test_parse_job_failure_without_details_valid_return_error(wrapped: bool) -> None:
    """失敗応答に発話詳細がなくても認識失敗として返す"""
    # Given: 詳細配列のない拒否応答
    payload = {"text": "", "code": "o", "message": "rejected"}
    data = {"session_id": "job1", "status": "completed", **({"results": payload} if wrapped else payload)}
    # When: 完了応答を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: 不正応答ではなく認識失敗を観測できる
    assert snapshot.is_error and snapshot.recognition.results == ()
    assert snapshot.error_code == "o"


@pytest.mark.parametrize(
    "changes",
    [
        {"status": ""},
        {"status": None},
        {"status": 3},
        {"status": "future\n"},
        {"session_id": "other"},
        {"text": None},
        {"code": None},
        {"message": []},
        {"segments": {}},
        {"results": {}},
    ],
)
def test_parse_job_invalid_required_fields_invalid_raise_AsyncHttpApiError(changes: dict[str, object]) -> None:
    """互換性向上でもIDや必須フィールドの検証を失わない"""
    # Given: 壊れた必須情報又は曖昧なエンベロープ
    data = {**completed(), **changes}
    # When / Then: 元の本文を保持した不正応答例外
    body = json.dumps(data).encode()
    with pytest.raises(AsyncHttpApiError) as caught:
        parse_job(body, "job1")
    assert caught.value.raw_body == body
