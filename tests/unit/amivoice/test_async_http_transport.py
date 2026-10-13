"""非同期HTTP公開APIから本物のローカル通信を検証する"""

import time

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncJobTimeoutError
from amivoice._async_http_transport import AsyncHttpConnection
from amivoice._params import RecognitionParams

from .async_mock_server import AsyncMockServer
from .recognition_mock_servers import parse_recognition_multipart
from .test_async_client import completed, queued


def test_client_local_http_valid_return_completed_and_multipart() -> None:
    """分割送信と分割UTF-8応答を公開APIで通して確認する"""
    # Given: 受付と飛び越した状態を返すサーバー
    responses = [(200, {"sessionid": "job1", "text": "..."}), (200, queued()), (200, completed())]
    audio = b"\x00\xff\r\naudio" * 10000
    with AsyncMockServer(responses) as server:
        client = AmiVoiceAsyncClient(
            api_key="dummy",
            grammar_file_names="-a-general",
            api_url=server.url,
            logging_opt_out=True,
            connect_timeout=1000,
            receive_timeout=1000,
        )
        # When: 登録と完了待機を実行する
        job = client.submit(audio, content_id="日本語", selected_channel=0)
        snapshot = client.wait(job.session_id, poll_interval=0.01, timeout=2)
        # Then: 元の音声と認証の配置を保持する
        assert snapshot.recognition.text == "認識"
        method, path, headers, body = server.received[0]
        assert method == "POST" and path == "/v2/recognitions"
        assert len(body) == int(headers["Content-Length"])
        assert headers["Authorization"] == "Bearer dummy"
        assert headers["User-Agent"].startswith("amivoice-api-client/")
        parts = parse_recognition_multipart(headers["Content-Type"], body)
        assert [name for name, _ in parts] == ["d", "a"]
        assert parts[-1][1] == audio
        assert b"loggingOptOut=True" in parts[0][1]
        assert b"audioFilterProperties=selectedChannel%3D0" in parts[0][1]
        assert b"dummy" not in body
        assert [call[1] for call in server.received[1:]] == ["/v2/recognitions/job1"] * 2
        assert all(call[2]["Authorization"] == "Bearer dummy" for call in server.received)


def test_wait_stalled_socket_edge_raise_before_server_response() -> None:
    """通信無制限でもwaitの締め切りでソケット待機を中断する"""
    # Given: 応答ヘッダを返さないサーバーと無制限の通信設定
    with AsyncMockServer([(200, queued())], stall=True) as server:
        client = AmiVoiceAsyncClient(api_key="dummy", api_url=server.url)
        start = time.monotonic()
        # When / Then: サーバー解放を待たずクライアントの締め切りで終了
        with pytest.raises(AsyncJobTimeoutError) as caught:
            client.wait("job1", timeout=0.1)
        assert time.monotonic() - start < 1.5
        assert caught.value.session_id == "job1" and caught.value.snapshot is None


def test_connection_https_proxy_valid_return_tunnel_only_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """プロキシ認証を認識リクエストに混入しない"""
    # Given: 生成された接続情報を確認する、ネットワーク接続はしない
    params = RecognitionParams(proxy_server_name="http://proxy-user:proxy-pass@proxy.test:8080")
    # When: HTTPS CONNECTを設定する
    connection, target, headers = AsyncHttpConnection._connection(
        "https://acp-api-async.amivoice.com/v2/recognitions", {"Authorization": "Bearer dummy"}, params, None
    )
    # Then: CONNECTヘッダだけにプロキシ認証を保持する
    assert connection.host == "proxy.test" and connection.port == 8080
    assert connection._tunnel_host == "acp-api-async.amivoice.com"
    assert "Proxy-Authorization" in connection._tunnel_headers
    assert "Proxy-Authorization" not in headers
    assert target == "/v2/recognitions"
    connection.close()
