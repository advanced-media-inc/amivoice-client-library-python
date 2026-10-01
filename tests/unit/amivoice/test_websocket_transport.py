"""汎用 WebSocket 通信境界の RFC 6455 回帰テスト"""

import io
import struct
from unittest.mock import MagicMock

import pytest

from amivoice._websocket_transport import WebSocketTransport
from amivoice.exceptions import RecognitionError


def _server_frame(payload: bytes, opcode: int = 1, *, final: bool = True) -> bytes:
    """サーバー側の非マスクフレームを構築する"""
    size = len(payload)
    header = bytes([(128 if final else 0) | opcode])
    if size < 126:
        return header + bytes([size]) + payload
    if size < 65536:
        return header + b"\x7e" + struct.pack("!H", size) + payload
    return header + b"\x7f" + struct.pack("!Q", size) + payload


def _transport(frames: bytes) -> WebSocketTransport:
    """ソケットの代わりに読み取りバッファを注入する"""
    transport = WebSocketTransport()
    transport._socket = MagicMock()
    transport._reader = io.BytesIO(frames)
    return transport


@pytest.mark.parametrize("size", [0, 125, 126, 65535, 65536])
def test_websocket_receive_lengths_valid_return_message(size: int) -> None:
    """各長さ表現のサーバーフレームを受信する"""
    # Given: 異なる長さのフレーム
    transport = _transport(_server_frame(b"a" * size))
    # When / Then: 本文が一致する
    assert transport.receive_message() == "a" * size


@pytest.mark.parametrize("size", [0, 125, 126, 65535, 65536])
def test_websocket_send_lengths_valid_return_masked_frame(size: int) -> None:
    """クライアント送信は必ずランダムマスクでエンコードする"""
    # Given: 音声を含むバイナリ本文
    transport = _transport(b"")
    payload = b"x" * size
    # When: バイナリフレームを送る
    transport.send_binary(payload)
    # Then: 長さとマスクを逆変換する
    frame = transport._socket.sendall.call_args.args[0]
    assert frame[0] == 0x82
    assert frame[1] & 128
    marker = frame[1] & 127
    offset = 2 if marker < 126 else (4 if marker == 126 else 10)
    mask = frame[offset : offset + 4]
    assert bytes(value ^ mask[index % 4] for index, value in enumerate(frame[offset + 4 :])) == payload


def test_websocket_fragmented_utf8_and_ping_valid_return_message() -> None:
    """UTF-8 の途中分割とインターリーブした Ping を処理する"""
    # Given: 分割されたマルチバイト文字
    data = "こんにちは".encode()
    transport = _transport(
        _server_frame(data[:2], final=False) + _server_frame(b"ping", opcode=9) + _server_frame(data[2:], opcode=0)
    )
    # When: 一つの論理メッセージを読む
    message = transport.receive_message()
    # Then: 自動 Pong と UTF-8 復元
    assert message == "こんにちは"
    assert transport._socket.sendall.call_args.args[0][0] == 0x8A


@pytest.mark.parametrize(
    "frame",
    [
        b"\xc1\x00",
        b"\x81\x80",
        b"\x83\x00",
        b"\x80\x00",
        b"\x09\x00",
        b"\x89\x7e\x00\x7e",
        b"\x81\x7f\x80\x00\x00\x00\x00\x00\x00\x00",
        _server_frame(b"\xff"),
        _server_frame(b"a", final=False) + _server_frame(b"b"),
        b"\x81\x7e\x00\x01a",
        b"\x81\x03a",
    ],
)
def test_websocket_receive_invalid_frame_invalid_raise_RecognitionError(frame: bytes) -> None:
    """予約ビット、マスク、長さ、継続、UTF-8、EOF の不正を拒否する"""
    # Given / When / Then: 不正な WebSocket フレーム
    transport = _transport(frame)
    with pytest.raises(RecognitionError):
        transport.receive_message()


def test_websocket_close_frame_invalid_raise_RecognitionError() -> None:
    """認識中の Close は終了を返信し例外を伝播する"""
    # Given: 正常 Close の受信
    transport = _transport(_server_frame(struct.pack("!H", 1000), opcode=8))
    # When / Then: 無限待機せず例外にする
    with pytest.raises(RecognitionError, match="closed"):
        transport.receive_message()
    assert transport._socket.sendall.call_args.args[0][0] == 0x88


def test_websocket_receive_oversized_invalid_raise_RecognitionError() -> None:
    """巨大な長さ指定で無制限にメモリを確保しない"""
    # Given: 本文を伴わない巨大フレーム長
    transport = _transport(b"\x81\x7f" + struct.pack("!Q", 1 << 40))
    # When / Then: 本文を読む前に拒否する
    with pytest.raises(RecognitionError, match="too large"):
        transport.receive_message()
