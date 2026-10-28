"""HTTPSプロキシのCONNECT処理もwaitの絶対期限内で中断する"""

import http.client
import socket
import socketserver
import threading
import time
from contextlib import suppress

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncJobTimeoutError
from amivoice._async_http_transport import _ConnectionDeadline


class SlowConnectHandler(socketserver.StreamRequestHandler):
    """CONNECT応答のヘッダをソケットタイムアウト未満の間隔で送る"""

    def handle(self) -> None:
        """接続を記録し、期限を超える長さの応答を分割する"""
        self.connection.settimeout(2)
        while self.rfile.readline() not in (b"\r\n", b""):
            pass
        self.server.connected.set()
        with suppress(OSError):
            self.wfile.write(b"HTTP/1.0 200 Connection established\r\n")
            for byte in b"X-Slow: " + b"x" * 100 + b"\r\n\r\n":
                if self.server.release.wait(0.02):
                    return
                self.wfile.write(bytes([byte]))


@pytest.mark.parametrize("receive_timeout", [0, 1000])
def test_wait_slow_proxy_connect_edge_raise_at_deadline(receive_timeout: int) -> None:
    """CONNECTヘッダが少しずつ到着してもwaitの期限で終了する"""
    # Given: 受信間隔は短いが応答全体は2秒以上かかるローカルプロキシ
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), SlowConnectHandler) as proxy:
        proxy.connected = threading.Event()
        proxy.release = threading.Event()
        thread = threading.Thread(target=proxy.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        thread.start()
        client = AmiVoiceAsyncClient(
            api_key="dummy",
            proxy_server_name=f"http://127.0.0.1:{proxy.server_address[1]}",
            receive_timeout=receive_timeout,
        )
        try:
            # When: HTTPSジョブの完了を短い期限で待つ
            start = time.monotonic()
            with pytest.raises(AsyncJobTimeoutError) as caught:
                client.wait("job1", timeout=0.15)
            elapsed = time.monotonic() - start
            # Then: CONNECTの終了まで待たず、期限例外に再開用IDを保持する
            assert proxy.connected.is_set()
            assert elapsed < 0.8
            assert caught.value.session_id == "job1"
            assert caught.value.snapshot is None
        finally:
            proxy.release.set()
            proxy.shutdown()
            thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.parametrize("replace_socket", [False, True])
def test_connection_deadline_socket_transfer_edge_return_interrupted_and_closed(replace_socket: bool) -> None:
    """ソケット所有権の移動後も期限で中断し、監視リソースを回収する"""
    # Given: 実ソケットと、TLSラップ同様に所有権を移すケース
    connection = http.client.HTTPConnection("example.test")
    sock, peer = socket.socketpair()
    connection._create_connection = lambda *args: sock
    guard = _ConnectionDeadline(connection, time.monotonic() + 0.1)
    connected = connection._create_connection(("example.test", 443), None, None)
    if replace_socket:
        connected = socket.socket(fileno=connected.detach())
    try:
        # When: 接続後の読み取りを待つ
        start = time.monotonic()
        assert connected.recv(1) == b""
        # Then: 所有権を移しても中断し、終了時は複製ソケットとタイマーを回収する
        assert time.monotonic() - start < 0.8
    finally:
        guard.close()
        connected.close()
        peer.close()
        connection.close()
    assert guard._socket.fileno() == -1
    assert not guard._timer.is_alive()


def test_connection_deadline_expired_after_connect_invalid_raise_and_close_socket() -> None:
    """接続成立時点ですでに期限切れならソケットを閉じる"""
    # Given: 名前解決等の遅延後に成立した接続を模擬する
    connection = http.client.HTTPConnection("example.test")
    sock, peer = socket.socketpair()
    connection._create_connection = lambda *args: sock
    guard = _ConnectionDeadline(connection, time.monotonic() - 1)
    try:
        # When / Then: CONNECT開始前に期限切れを通知し接続を残さない
        with pytest.raises(TimeoutError):
            connection._create_connection(("example.test", 443), None, None)
        assert sock.fileno() == -1
    finally:
        guard.close()
        peer.close()
        connection.close()
