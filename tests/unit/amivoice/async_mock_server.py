"""非同期HTTPのPOSTとGETをloopback上で再現する"""

import json
import threading
from collections import deque
from contextlib import AbstractContextManager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType


class _Handler(BaseHTTPRequestHandler):
    """要求を記録して合成JSONをチャンク転送する"""

    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:
        """音声のmultipartを記録する"""
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.received.append(("POST", self.path, dict(self.headers), body))
        self._respond()

    def do_GET(self) -> None:
        """状態取得と待機のGETを記録する"""
        self.server.received.append(("GET", self.path, dict(self.headers), b""))
        self._respond()

    def _respond(self) -> None:
        server = self.server
        if server.stall:
            server.release.wait(timeout=3)
        if not server.responses:
            status, data = 500, {"error": "unexpected request"}
        else:
            status, data = server.responses.popleft()
        payload = json.dumps(data, ensure_ascii=False).encode()
        with suppress(BrokenPipeError, ConnectionResetError):
            self.send_response(status)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for offset in range(0, len(payload), 7):
                chunk = payload[offset : offset + 7]
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        """認証を含むログも表示しない"""


class AsyncMockServer(AbstractContextManager):
    """ローカルサーバーのスレッドと遅延応答の寿命を管理する"""

    def __init__(self, responses: list[tuple[int, object]], *, stall: bool = False) -> None:
        """応答列と受信記録を用意する"""
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.responses = deque(responses)
        self._server.received = []
        self._server.stall = stall
        self._server.release = threading.Event()
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)

    @property
    def url(self) -> str:
        """ローカルのv2エンドポイント"""
        return f"http://127.0.0.1:{self._server.server_port}/v2/recognitions"

    @property
    def received(self) -> list[tuple[str, str, dict[str, str], bytes]]:
        """記録したメソッド、パス、ヘッダ、本文"""
        return self._server.received

    def __enter__(self) -> "AsyncMockServer":
        """サーバーを開始する"""
        self._thread.start()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        """遅延応答を解放し例外時も終了する"""
        self._server.release.set()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=3)
        assert not self._thread.is_alive()
