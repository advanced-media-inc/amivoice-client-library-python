"""ジョブ失敗の原因コードと再試行の目安を検証する"""

import json

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncJobError, RecognitionSettings
from amivoice._async_models import parse_job

from .test_async_client import RecordingTransport


@pytest.mark.parametrize(
    ("message", "code", "retryable"),
    [
        ("ERROR: amineth_code='o', amineth_message='rejected'", "o", False),
        ("ERROR: amineth_code='b', amineth_message='server busy'", "b", True),
        ("ERROR: amineth_code='-', amineth_message='failure'", "-", True),
        ("unclassified failure", None, None),
        ("amineth_code='unknown'", None, None),
        ("amineth_code='o' amineth_code='b'", None, None),
        ("not_amineth_code='o'", None, None),
    ],
)
def test_parse_job_failure_valid_return_retry_hint(message: str, code: str | None, retryable: bool | None) -> None:
    """単一の原因コードだけを解釈し未知の失敗を断定しない"""
    # Given: ジョブがerrorになった公式形式の応答
    data = {"session_id": "job1", "status": "error", "error_message": message}
    # When: スナップショットと例外を作成する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    error = AsyncJobError("Async HTTP job failed", snapshot)
    # Then: 同じ構造化情報を参照でき、表示には本文を含めない
    assert snapshot.error_code == error.error_code == code
    assert snapshot.is_retryable is retryable and error.is_retryable is retryable
    assert message not in str(error)


@pytest.mark.parametrize("status", ["queued", "processing"])
def test_parse_job_pending_valid_return_unknown_retry_hint(status: str) -> None:
    """処理中のジョブに再試行を勧めない"""
    # Given: 終端に達していない状態
    body = json.dumps({"session_id": "job1", "status": status}).encode()
    # When: 状態を解析する
    snapshot = parse_job(body, "job1")
    # Then: 失敗コードと再試行可否は未確定
    assert snapshot.error_code is None and snapshot.is_retryable is None


@pytest.mark.parametrize(("code", "retryable"), [("o", False), ("+", None), ("", None)])
def test_parse_job_recognition_valid_return_conservative_retry_hint(code: str, retryable: bool | None) -> None:
    """認識拒否は再試行不可とし他の認識コードを基盤障害と断定しない"""
    # Given: 同期互換形式の認識結果
    data = {
        "session_id": "job1",
        "status": "completed",
        "code": code,
        "message": "failed" if code else "",
        "text": "" if code else "recognized",
        "results": [],
    }
    # When: 完了結果を解析する
    snapshot = parse_job(json.dumps(data).encode(), "job1")
    # Then: 公式のジョブerrorの再試行案内を全認識エラーへ拡張しない
    assert snapshot.error_code == (code or None)
    assert snapshot.is_retryable is retryable


@pytest.mark.parametrize("recognition_failure", [False, True])
def test_diarization_failed_job_valid_return_snapshot_or_raise(recognition_failure: bool) -> None:
    """有効時も状態取得・例外化・例外抑制の既存経路を維持する"""
    # Given: ジョブ失敗と認識拒否の合成応答、音声長固有のエラーとは断定しない
    response = {"session_id": "job1", "status": "error", "error_message": "unclassified failure"}
    if recognition_failure:
        response = {"session_id": "job1", "status": "completed", "code": "o", "message": "rejected", "text": ""}
    transport = RecordingTransport([response, response, response])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport, settings=RecognitionSettings(speaker_diarization=True))
    # When: 観測・既定の待機・例外抑制を順に実行する
    snapshot = client.get_job("job1")
    with pytest.raises(AsyncJobError) as caught:
        client.wait("job1")
    observed = client.wait("job1", raise_on_error=False)
    # Then: エラースナップショットをそのまま提供する
    assert snapshot.is_error and observed.is_error and caught.value.snapshot.is_error
    assert snapshot.data == observed.data == caught.value.snapshot.data == response
