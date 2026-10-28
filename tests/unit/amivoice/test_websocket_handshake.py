"""CONNECTとUpgradeのHTTP応答に対する互換性と検証境界"""

from unittest.mock import patch

import pytest

from amivoice._params import RecognitionParams
from amivoice._websocket_connection import WebSocketConnection
from amivoice.exceptions import ConnectionFailedError

_WEBSOCKET_NONCE = b"the sample nonce"
_WEBSOCKET_ACCEPT = b"s3pPLMBiTxaQ9kYGzzhZRbK+xOo="


def _upgrade_response(extra_headers: bytes = b"") -> bytes:
    """RFC 6455のnonceに対応するUpgrade応答を組み立てる"""
    return (
        b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "
        + _WEBSOCKET_ACCEPT
        + b"\r\n"
        + extra_headers
        + b"\r\n"
    )


@pytest.mark.parametrize(
    "proxy_response",
    [
        b"HTTP/1.0 200 Connection established\r\n\r\n",
        b"HTTP/1.1 200 Connection established\r\n\r\n",
        b"HTTP/1.1 200 OK\r\nVia: 1.1 first\r\nVia: 1.1 second\r\n\r\n",
    ],
)
@pytest.mark.parametrize("scheme", ["ws", "wss"])
def test_websocket_connect_proxy_response_valid_return_connection(proxy_response: bytes, scheme: str) -> None:
    """CONNECTではHTTP/1.0と複数のViaを受け付ける"""
    # Given: CONNECTとUpgradeを順番に返すプロキシ接続
    with (
        patch("socket.create_connection") as factory,
        patch("ssl.create_default_context") as tls_context,
        patch("secrets.token_bytes", return_value=_WEBSOCKET_NONCE),
    ):
        sock = factory.return_value
        tls_context.return_value.wrap_socket.return_value = sock
        sock.recv.side_effect = [proxy_response, _upgrade_response()]
        connection = WebSocketConnection()
        try:
            # When: プロキシ経由でWebSocketを接続する
            connection.connect(f"{scheme}://example.test/v1/", "dummy", RecognitionParams(proxy_server_name="proxy.test:8080"))
            # Then: CONNECT後にUpgradeを送り、必要ならTLSも適用する
            requests = [call.args[0] for call in sock.sendall.call_args_list]
            assert requests[0].startswith(b"CONNECT example.test:")
            assert requests[1].startswith(b"GET /v1/ HTTP/1.1\r\n")
            assert tls_context.return_value.wrap_socket.call_count == (1 if scheme == "wss" else 0)
        finally:
            connection.close()


@pytest.mark.parametrize(
    "extra_headers",
    [
        b"Set-Cookie: first=1\r\nSet-Cookie: second=2\r\n",
        b"Via: 1.1 first\r\nVia: 1.1 second\r\n",
        b"Connection: keep-alive\r\n",
    ],
)
def test_websocket_connect_repeated_response_headers_valid_return_connection(extra_headers: bytes) -> None:
    """CookieやViaの重複を許容し、Connectionのリスト値を検証する"""
    # Given: 正常なUpgrade応答に追加された重複ヘッダ
    with patch("socket.create_connection") as factory, patch("secrets.token_bytes", return_value=_WEBSOCKET_NONCE):
        sock = factory.return_value
        sock.recv.return_value = _upgrade_response(extra_headers)
        connection = WebSocketConnection()
        try:
            # When: Upgrade応答を検証する
            connection.connect("ws://127.0.0.1/v1/", "dummy", RecognitionParams())
            # Then: 正常なWebSocket接続として保持する
            assert connection._socket is sock
        finally:
            connection.close()


@pytest.mark.parametrize(
    "response",
    [
        _upgrade_response(b"Sec-WebSocket-Accept: " + _WEBSOCKET_ACCEPT + b"\r\n"),
        _upgrade_response().replace(_WEBSOCKET_ACCEPT, b"invalid"),
        _upgrade_response().replace(b"HTTP/1.1", b"HTTP/1.0"),
        _upgrade_response(b"invalid-header\r\n"),
    ],
)
def test_websocket_connect_invalid_upgrade_response_invalid_raise_ConnectionFailedError(response: bytes) -> None:
    """Acceptの重複や不一致、不正なUpgrade応答を引き続き拒否する"""
    # Given: 接続互換性の改善でも受理してはいけない応答
    with patch("socket.create_connection") as factory, patch("secrets.token_bytes", return_value=_WEBSOCKET_NONCE):
        sock = factory.return_value
        sock.recv.return_value = response
        connection = WebSocketConnection()
        # When / Then: 応答を拒否し、接続を回収する
        with pytest.raises(ConnectionFailedError):
            connection.connect("ws://127.0.0.1/v1/", "dummy", RecognitionParams())
        assert connection._socket is None
        sock.close.assert_called_once()


def test_websocket_connect_proxy_rejection_invalid_raise_ConnectionFailedError() -> None:
    """HTTP/1.0を受理してもプロキシの認証失敗は拒否する"""
    # Given: 認証失敗のCONNECT応答
    with patch("socket.create_connection") as factory:
        sock = factory.return_value
        sock.recv.return_value = b"HTTP/1.0 407 Proxy Authentication Required\r\n\r\n"
        connection = WebSocketConnection()
        # When / Then: Upgradeを送らず、接続を回収する
        with pytest.raises(ConnectionFailedError):
            connection.connect("ws://127.0.0.1/v1/", "dummy", RecognitionParams(proxy_server_name="proxy.test:8080"))
        assert sock.sendall.call_count == 1
        sock.close.assert_called_once()
