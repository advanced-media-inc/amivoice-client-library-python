"""公開APIの送受信をloopback上で再現する認識モックサーバー"""

import base64
import hashlib
import socket
import struct
import threading
from concurrent.futures import Future
from contextlib import AbstractContextManager
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType


def parse_recognition_multipart(content_type: str, body: bytes) -> list[tuple[str, bytes]]:
    """標準のMIMEパーサでパート名と内容を取得する

    Args:
        content_type (str): boundaryを含むContent-Type
        body (bytes): multipart本文

    Returns:
        list[tuple[str, bytes]]: 送信順のパート名とバイト列
    """
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    return [
        (part.get_param("name", header="Content-Disposition"), part.get_payload(decode=True)) for part in message.iter_parts()
    ]


class _RecordedHttpHandler(BaseHTTPRequestHandler):
    """受信リクエストを記録し、設定済みのJSONをHTTP200で返す"""

    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        """本文を改変せず記録し、UTF-8を分割してチャンク転送する"""
        server = self.server
        body = self.rfile.read(int(self.headers["Content-Length"]))
        server.received.append((self.path, dict(self.headers), body))
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        payload = server.response_body
        for offset in range(0, len(payload), 7):
            chunk = payload[offset : offset + 7]
            self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        """ダミーキーを含む通信ログも出力しない"""


class RecordedHttpServer(AbstractContextManager):
    """ローカルHTTPサーバーの起動と回収を管理する"""

    def __init__(self, response_body: bytes) -> None:
        """応答と受信記録をサーバーごとに分離する"""
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordedHttpHandler)
        self._server.response_body = response_body
        self._server.received = []
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    @property
    def url(self) -> str:
        """資格情報を含まないローカル認識URLを返す"""
        return f"http://127.0.0.1:{self._server.server_port}/v1/recognize"

    @property
    def received(self) -> list[tuple[str, dict[str, str], bytes]]:
        """送信パスとヘッダと本文を返す"""
        return self._server.received

    def __enter__(self) -> "RecordedHttpServer":
        """サーバーを起動する"""
        self._thread.start()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        """テストが失敗してもソケットとスレッドを回収する"""
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=3)
        assert not self._thread.is_alive()


def read_socket_bytes(peer: socket.socket, count: int) -> bytes:
    """指定されたバイト数を読み取る、途中切断はテスト失敗にする"""
    data = bytearray()
    while len(data) < count:
        chunk = peer.recv(count - len(data))
        if not chunk:
            raise AssertionError("Mock WebSocket received unexpected EOF")
        data.extend(chunk)
    return bytes(data)


def read_client_websocket_frame(peer: socket.socket) -> tuple[int, bytes]:
    """クライアントフレームのmaskを検査し、本文を復元する"""
    header = read_socket_bytes(peer, 2)
    assert header[1] & 0x80, "Client WebSocket frames must be masked"
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", read_socket_bytes(peer, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", read_socket_bytes(peer, 8))[0]
    mask = read_socket_bytes(peer, 4)
    payload = read_socket_bytes(peer, length)
    return header[0] & 15, bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))


def send_server_websocket_frame(peer: socket.socket, payload: bytes, *, opcode: int = 1, final: bool = True) -> None:
    """サーバーフレームをmaskなしで送る"""
    first = opcode | (0x80 if final else 0)
    length = len(payload)
    if length < 126:
        header = bytes((first, length))
    elif length < 65536:
        header = bytes((first, 126)) + struct.pack("!H", length)
    else:
        header = bytes((first, 127)) + struct.pack("!Q", length)
    peer.sendall(header + payload)


class RecordedWebSocketServer(AbstractContextManager):
    """Upgradeとs/p/eを検査して、匿名化したイベント列を再生する"""

    def __init__(self, packets: list[str], *, fragment_final: bool = False, end_error: str | None = None) -> None:
        """イベント列と追加の通信条件を保持する"""
        self._packets = packets
        self._fragment_final = fragment_final
        self._end_error = end_error
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self._listener.settimeout(3)
        self._completion: Future[None] = Future()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self.upgrade_request = b""
        self.frames: list[tuple[int, bytes]] = []
        self.pongs: list[bytes] = []

    @property
    def url(self) -> str:
        """資格情報を含まないローカルWebSocket URLを返す"""
        return f"ws://127.0.0.1:{self._listener.getsockname()[1]}/v1/"

    def __enter__(self) -> "RecordedWebSocketServer":
        """受信処理を起動する"""
        self._thread.start()
        return self

    def _upgrade(self, peer: socket.socket) -> None:
        request = bytearray()
        while b"\r\n\r\n" not in request:
            request.extend(read_socket_bytes(peer, 1))
        self.upgrade_request = bytes(request)
        key = next(line.split(b": ", 1)[1] for line in request.split(b"\r\n") if line.startswith(b"Sec-WebSocket-Key:"))
        # RFC 6455のUpgrade応答にはSHA-1が必要、認証・パスワードのハッシュ用途ではない
        # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
        digest = hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11", usedforsecurity=False).digest()
        peer.sendall(
            b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: "
            + base64.b64encode(digest)
            + b"\r\n\r\n"
        )

    def _replay(self, peer: socket.socket) -> None:
        for packet in self._packets:
            if packet == "s":
                continue
            payload = packet.encode("utf-8")
            if self._fragment_final and packet.startswith("A "):
                split = next(index + 1 for index, byte in enumerate(payload) if byte >= 128)
                send_server_websocket_frame(peer, payload[:split], final=False)
                send_server_websocket_frame(peer, b"probe", opcode=9)
                opcode, pong = read_client_websocket_frame(peer)
                assert opcode == 10
                self.pongs.append(pong)
                send_server_websocket_frame(peer, payload[split:], opcode=0)
            else:
                send_server_websocket_frame(peer, payload)

    def _serve(self) -> None:
        try:
            peer, _ = self._listener.accept()
            with peer:
                peer.settimeout(3)
                self._upgrade(peer)
                first = read_client_websocket_frame(peer)
                assert first[0] == 1 and first[1].startswith(b"s ")
                self.frames.append(first)
                send_server_websocket_frame(peer, b"s")
                while True:
                    frame = read_client_websocket_frame(peer)
                    self.frames.append(frame)
                    if frame == (1, b"e"):
                        break
                    assert frame[0] == 2 and frame[1].startswith(b"p")
                if self._end_error:
                    send_server_websocket_frame(peer, self._end_error.encode())
                else:
                    self._replay(peer)
            self._completion.set_result(None)
        except Exception as error:
            self._completion.set_exception(error)

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        """スレッドの例外を親テストに伝え、ソケットを残さない"""
        self._listener.close()
        self._thread.join(timeout=4)
        assert not self._thread.is_alive()
        if exc_type is None:
            self._completion.result(timeout=0)
