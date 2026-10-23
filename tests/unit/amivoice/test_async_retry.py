"""待機中のGETだけを期限内で限定再試行する"""

import pytest

from amivoice import (
    AmiVoiceAsyncClient,
    AsyncHttpApiError,
    AsyncJobTimeoutError,
    ConfigurationError,
    ConnectionFailedError,
    RecognitionSettings,
)

from .test_async_client import RecordingTransport, completed, queued


def fake_clock(client: AmiVoiceAsyncClient, monkeypatch: pytest.MonkeyPatch) -> tuple[list[float], list[float]]:
    """睡眠を記録する仮想時計を設定する"""
    times, sleeps = [0.0], []
    monkeypatch.setattr(client, "_clock", lambda: times[0])

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        times[0] += seconds

    monkeypatch.setattr(client, "_sleep", sleep)
    return times, sleeps


@pytest.mark.parametrize(
    "failure",
    [
        OSError("lost"),
        ConnectionFailedError("lost"),
        (429, b"busy"),
        (500, b"error"),
        (502, b"error"),
        (503, b"error"),
        (504, b"error"),
    ],
)
def test_wait_transient_failure_valid_return_after_retry(failure: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """一時的なGET失敗だけを再試行する"""
    # Given: 一時障害後に成功するジョブ
    transport = RecordingTransport([failure, failure, completed()])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    times, sleeps = fake_clock(client, monkeypatch)
    # When: 期限内で完了待機する
    snapshot = client.wait("job1", timeout=10)
    # Then: 1秒、2秒のバックオフ後に完了する
    assert snapshot.status == "completed" and times[0] == 3
    assert sleeps == [1, 2]
    assert all(call[0] == "GET" and call[-1] == 10 for call in transport.calls)


@pytest.mark.parametrize("status", [200, 400, 401, 403, 404, 501])
def test_wait_permanent_failure_invalid_raise_without_retry(status: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """認証失敗や不正応答を繰り返さない"""
    # Given: 再試行対象でない応答
    transport = RecordingTransport([(status, b"invalid")])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    _, sleeps = fake_clock(client, monkeypatch)
    # When / Then: 元のHTTP例外を送出する
    with pytest.raises(AsyncHttpApiError):
        client.wait("job1")
    assert len(transport.calls) == 1 and not sleeps


@pytest.mark.parametrize("max_retries", [0, 2])
def test_wait_retry_limit_edge_raise_last_failure(max_retries: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """設定した再試行回数を超えない"""
    # Given: 恒常的な通信失敗
    transport = RecordingTransport([OSError("lost")] * (max_retries + 1))
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    _, sleeps = fake_clock(client, monkeypatch)
    # When / Then: 上限後に接続例外を返す
    with pytest.raises(ConnectionFailedError):
        client.wait("job1", max_retries=max_retries)
    assert len(transport.calls) == max_retries + 1 and len(sleeps) == max_retries


def test_wait_backoff_deadline_edge_raise_with_last_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """バックオフも全体期限に含め最後の観測を失わない"""
    # Given: 一度状態を取得した後に障害になるジョブ
    transport = RecordingTransport([queued(), (503, b"busy"), (503, b"busy")])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    times, sleeps = fake_clock(client, monkeypatch)
    # When / Then: 残り時間だけ待ち、余分なGETを送らない
    with pytest.raises(AsyncJobTimeoutError) as caught:
        client.wait("job1", poll_interval=1, timeout=2.5)
    assert caught.value.snapshot.status == "queued"
    assert times[0] == 2.5 and sleeps == [1, 1, 0.5]
    assert len(transport.calls) == 3


def test_wait_success_resets_valid_return_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    """正常な状態取得ごとに連続失敗の上限をリセットする"""
    # Given: 状態取得の間に一度ずつ障害が起きる
    transport = RecordingTransport([(500, b"busy"), queued(), (500, b"busy"), completed()])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    fake_clock(client, monkeypatch)
    # When: 連続失敗1回まで再試行する
    snapshot = client.wait("job1", max_retries=1)
    # Then: 正常応答の後にも再試行できる
    assert snapshot.status == "completed" and len(transport.calls) == 4


def test_wait_large_backoff_edge_return_capped_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """非常に大きいバックオフ指定でも30秒に制限する"""
    # Given: 再試行が必要なジョブ
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([(500, b"busy"), completed()]))
    _, sleeps = fake_clock(client, monkeypatch)
    # When: 大きい有限バックオフを指定する
    client.wait("job1", retry_backoff=1e300)
    # Then: 巨大sleepやオーバーフローを避ける
    assert sleeps == [30]


@pytest.mark.parametrize(
    "settings",
    [
        {"max_retries": -1},
        {"max_retries": True},
        {"max_retries": 1.5},
        {"retry_backoff": 0},
        {"retry_backoff": float("inf")},
        {"retry_backoff": True},
    ],
)
def test_wait_invalid_retry_settings_invalid_raise_ConfigurationError(settings: dict[str, object]) -> None:
    """再試行設定を通信前に検証する"""
    # Given: 通信しないクライアント
    transport = RecordingTransport([])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    # When / Then: 設定エラーとして拒否する
    with pytest.raises(ConfigurationError):
        client.wait("job1", **settings)
    assert not transport.calls


def test_get_job_transient_failure_invalid_raise_without_retry() -> None:
    """単発状態取得の通信回数は変更しない"""
    # Given: 単発GETの障害
    transport = RecordingTransport([(500, b"busy")])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    # When / Then: 再試行せず呼び出し元へ戻る
    with pytest.raises(AsyncHttpApiError):
        client.get_job("job1")
    assert len(transport.calls) == 1


@pytest.mark.parametrize("resume_operation", ["wait", "get_job"])
def test_wait_diarization_timeout_edge_return_resumed_job(resume_operation: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """話者設定有効時も待機打ち切り後に同じIDで再開できる"""
    # Given: 締め切り後に完了する合成ジョブ
    transport = RecordingTransport([queued(), completed()])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport, settings=RecognitionSettings(speaker_diarization=True))
    fake_clock(client, monkeypatch)
    # When: 待機上限で一度戻り、そのIDを再利用する
    with pytest.raises(AsyncJobTimeoutError) as caught:
        client.wait("job1", timeout=1, poll_interval=2)
    snapshot = getattr(client, resume_operation)(caught.value.session_id)
    # Then: 再POSTせず結果を観測する
    assert snapshot.status == "completed" and caught.value.snapshot.status == "queued"
    assert [call[0] for call in transport.calls] == ["GET", "GET"]
