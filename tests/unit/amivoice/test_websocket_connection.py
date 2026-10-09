"""ローカルサーバとソケットで認識通信を検証する"""

import base64
import hashlib
import socket
import threading
from unittest.mock import patch

import pytest

from amivoice._params import RecognitionParams
from amivoice._websocket_connection import WebSocketConnection
from amivoice.exceptions import RecognitionError

from .recognition_mock_servers import read_client_websocket_frame as _read_client_frame


@pytest.mark.parametrize("size", [0, 125, 126, 65535, 65536])
def test_websocket_send_frame_length_valid_return_masked_frame(size: int) -> None:
    """3種類のフレーム長を正しくマスクする"""
    # Given: ソケットの代わりに送信記録を残すモック
    connection = WebSocketConnection()
    with patch("socket.socket") as factory:
        sock = factory.return_value
        connection._socket = sock
        # When: テキストを送信する
        connection.send_text("x" * size)
        raw = sock.sendall.call_args.args[0]
    # Then: maskビットと復元した長さが一致する
    offset = 2 if size < 126 else (4 if size < 65536 else 10)
    mask = raw[offset : offset + 4]
    assert raw[1] & 0x80
    assert bytes(c ^ mask[i % 4] for i, c in enumerate(raw[offset + 4 :])) == b"x" * size


def test_websocket_receive_fragmented_utf8_valid_return_text_and_pong() -> None:
    """分割UTF-8の途中にPingが入っても正しく再構成する"""
    # Given: 日本語の1文字を分割したフレームとPing
    client, peer = socket.socketpair()
    connection = WebSocketConnection()
    connection._socket = client
    payload = "あ".encode()
    peer.sendall(b"\x01\x01" + payload[:1] + b"\x89\x01z" + b"\x80\x02" + payload[1:])
    try:
        # When: テキストを受信する
        text = connection.receive_text()
        # Then: UTF-8を結合しPongをマスクして返す
        assert text == "あ"
        assert _read_client_frame(peer) == (10, b"z")
    finally:
        connection.close()
        peer.close()


@pytest.mark.parametrize("data", [b"\x81\x80", b"\x80\x00", b"\x09\x00", b"\xc1\x00", b"\x81\x7e\x00\x01", b"\x88\x01x"])
def test_websocket_receive_invalid_frame_invalid_raise_RecognitionError(data: bytes) -> None:
    """未対応フラグや不正な長さを拒否する"""
    # Given: 不正なフレーム
    client, peer = socket.socketpair()
    connection = WebSocketConnection()
    connection._socket = client
    peer.sendall(data)
    try:
        # When / Then: 受信時に例外を送出する
        with pytest.raises(RecognitionError):
            connection.receive_text()
    finally:
        connection.close()
        peer.close()


def test_websocket_upgrade_response_valid_return_buffered_frame() -> None:
    """Upgrade直後の同じrecvに届いたフレームを失わない"""
    # Given: 本物のUpgradeを模倣するlocalhostサーバ
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    seen = []

    def serve() -> None:
        peer, _ = listener.accept()
        with peer:
            request = bytearray()
            while b"\r\n\r\n" not in request:
                request.extend(peer.recv(4096))
            seen.append(bytes(request))
            key = next(line.split(b": ", 1)[1] for line in request.split(b"\r\n") if line.startswith(b"Sec-WebSocket-Key:"))
            # RFC 6455のUpgrade応答を生成するためのSHA-1
            # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
            accept = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11", usedforsecurity=False).digest())
            peer.sendall(
                b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "
                + accept
                + b"\r\n\r\n\x81\x01s"
            )
            peer.recv(4096)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    connection = WebSocketConnection()
    try:
        # When: 接続し最初のテキストを読む
        connection.connect(f"ws://127.0.0.1:{listener.getsockname()[1]}/v1/", "dummy", RecognitionParams(receive_timeout=1000))
        # Then: 認証ヘッダとバッファされた応答を確認する
        assert connection.receive_text() == "s"
        assert b"Authorization: Bearer dummy\r\n" in seen[0]
    finally:
        connection.close()
        listener.close()
        thread.join(timeout=2)
