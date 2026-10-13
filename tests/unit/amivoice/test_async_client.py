"""公開クライアントの作成、取得、待機と設定の継承を検証する"""

import json
from collections import deque

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncHttpApiError, AsyncJobError, AsyncJobTimeoutError, ConfigurationError
from amivoice._async_audio import MultipartUpload
from amivoice._params import RecognitionParams


class RecordingTransport:
    """通信をせず要求と応答を記録する"""

    def __init__(self, responses: list[object]) -> None:
        """用意した応答を順に返す"""
        self.responses = deque(responses)
        self.calls = []

    def request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: MultipartUpload | None,
        params: RecognitionParams,
        *,
        deadline: float | None = None,
    ) -> tuple[int, bytes]:
        """本文を分割読込し各要求を記録する"""
        self.calls.append((method, url, headers, b"".join(body.chunks()) if body is not None else None, params, deadline))
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        if isinstance(response, tuple):
            return response
        return 200, json.dumps(response).encode()


def queued(status: str = "queued") -> dict[str, object]:
    """待機状態の合成応答"""
    return {"session_id": "job1", "status": status}


def completed() -> dict[str, object]:
    """完了の合成応答"""
    return {
        **queued("completed"),
        "code": "",
        "message": "",
        "text": "認識",
        "segments": [{"text": "認識", "results": [{"text": "認識", "tokens": [{"written": "認識"}]}]}],
    }


def test_submit_overrides_valid_return_job_and_encoded_domain() -> None:
    """既定値を継承し明示NoneとFalseを区別する"""
    # Given: 既定のログ保存なしと辞書
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}])
    client = AmiVoiceAsyncClient(
        api_key="dummy",
        grammar_file_names="-a-general",
        logging_opt_out=True,
        profile_id=":test",
        content_id="old",
        transport=transport,
    )
    # When: 既定値を今回だけ解除する
    job = client.submit(b"audio", profile_id=None, logging_opt_out=False, content_id="日本 語", compatible_with_sync=True)
    # Then: 非同期はURLをnologへ変えずパラメータで制御
    assert job.session_id == "job1"
    method, url, headers, body, _, _ = transport.calls[0]
    assert method == "POST" and url.endswith("/v2/recognitions")
    assert headers["Authorization"] == "Bearer dummy"
    assert b"loggingOptOut=False" in body and b"compatibleWithSync=True" in body
    assert b"profileId=" not in body and b"dummy" not in body
    assert b"contentId=%E6%97%A5%E6%9C%AC%20%E8%AA%9E" in body


def test_get_job_no_engine_valid_return_snapshot() -> None:
    """保存済みIDの取得に認識エンジンは不要"""
    # Given: エンジンを設定しない新しいクライアント
    transport = RecordingTransport([queued()])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    # When: IDから再開する
    snapshot = client.get_job("job1")
    # Then: GETに音声本文を送らない
    assert snapshot.status == "queued"
    assert transport.calls[0][0] == "GET" and transport.calls[0][3] is None


def test_wait_skipped_states_valid_return_completed(monkeypatch: pytest.MonkeyPatch) -> None:
    """中間状態を全て観測しなくても完了する"""
    # Given: queuedからcompletedへ飛ぶ状態列と仮想時計
    transport = RecordingTransport([queued(), completed()])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    times = [0.0]
    monkeypatch.setattr(client, "_clock", lambda: times[0])
    monkeypatch.setattr(client, "_sleep", lambda seconds: times.__setitem__(0, times[0] + seconds))
    # When: 認識完了を待つ
    snapshot = client.wait("job1", poll_interval=2, timeout=10)
    # Then: 終端結果と全体締め切りを取得する
    assert snapshot.recognition.text == "認識"
    assert times[0] == 2
    assert all(call[-1] == 10 for call in transport.calls)


def test_wait_timeout_edge_raise_with_last_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """待機を打ち切ってもIDと最後の状態を保持する"""
    # Given: まだ待機しているジョブ
    transport = RecordingTransport([queued()])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    times = [0.0]
    monkeypatch.setattr(client, "_clock", lambda: times[0])
    monkeypatch.setattr(client, "_sleep", lambda seconds: times.__setitem__(0, times[0] + seconds))
    # When / Then: 残り時間だけsleepして終了
    with pytest.raises(AsyncJobTimeoutError) as caught:
        client.wait("job1", poll_interval=10, timeout=3)
    assert caught.value.session_id == "job1"
    assert caught.value.snapshot.status == "queued"
    assert len(transport.calls) == 1 and times[0] == 3


@pytest.mark.parametrize("raise_on_error", [True, False])
def test_wait_job_error_valid_return_or_raise(raise_on_error: bool) -> None:
    """ジョブ失敗の観測と例外化を切り替える"""
    # Given: エラー応答
    error = {**queued("error"), "error_message": "secret-dummy failed"}
    client = AmiVoiceAsyncClient(api_key="secret-dummy", transport=RecordingTransport([error]))
    # When / Then: 観測時は失敗の状態、既定では安全な例外
    if raise_on_error:
        with pytest.raises(AsyncJobError) as caught:
            client.wait("job1")
        assert "secret-dummy" not in str(caught.value)
        assert caught.value.snapshot.data == error
    else:
        assert client.wait("job1", raise_on_error=False).is_error


@pytest.mark.parametrize("session_id", ["", "..", "job/other", "job\\other", "job\nother", None])
def test_get_job_invalid_id_invalid_raise_ConfigurationError(session_id: object) -> None:
    """IDをURLへ安全に追加する"""
    # Given: パスへ混入できるID
    transport = RecordingTransport([])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    # When / Then: 通信前に拒否
    with pytest.raises(ConfigurationError):
        client.get_job(session_id)
    assert not transport.calls


@pytest.mark.parametrize(
    "settings",
    [
        {"poll_interval": 0},
        {"poll_interval": float("nan")},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": True},
        {"timeout": float("inf")},
        {"raise_on_error": 1},
    ],
)
def test_wait_invalid_settings_invalid_raise_ConfigurationError(settings: dict[str, object]) -> None:
    """待機の不正設定を通信前に拒否する"""
    # Given: 不正な待機設定
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([]))
    # When / Then: 設定エラー
    with pytest.raises(ConfigurationError):
        client.wait("job1", **settings)


def test_get_job_http_404_invalid_raise_detail() -> None:
    """404を期限切れや認識エラーと断定しない"""
    # Given: 状態取得APIの404
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([(404, b"not found")]))
    # When / Then: HTTPの詳細を保持
    with pytest.raises(AsyncHttpApiError) as caught:
        client.get_job("job1")
    assert caught.value.status_code == 404 and caught.value.session_id == "job1"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/v1/recognitions",
        "http://example.com/v2/recognitions",
        "https://example.com/v2/recognitions?u=key",
        "https://user:pass@example.com/v2/recognitions",
    ],
)
def test_client_invalid_endpoint_invalid_raise_ConfigurationError(url: str) -> None:
    """v1と認証漏洩につながるURLを拒否する"""
    # Given: 不正な接続先
    # When / Then: コンストラクタで拒否する
    with pytest.raises(ConfigurationError):
        AmiVoiceAsyncClient(api_key="dummy", api_url=url)
