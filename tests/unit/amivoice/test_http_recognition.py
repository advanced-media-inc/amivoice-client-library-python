"""ローカルサーバとソケットで認識通信を検証する"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from unittest.mock import patch

import pytest

from amivoice._http_recognition import HttpRecognitionConnection
from amivoice._params import RecognitionParams
from amivoice.exceptions import ConnectionFailedError


class _RecognitionHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    received: ClassVar[list[tuple[str, bytes]]] = []

    def do_POST(self) -> None:
        """チャンク転送の認識結果を返す"""
        self.received.append((self.headers.get("Authorization", ""), self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        for data in [b'{"text":"hello",', b'"code":"","message":""}']:
            self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def log_message(self, format: str, *args: object) -> None:
        """テスト用の通信ログは出さない"""


def test_http_request_chunked_response_valid_return_body() -> None:
    """認証情報を本文URLに含めずチャンク転送を読める"""
    # Given: localhostだけで動くHTTPサーバ
    _RecognitionHandler.received = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecognitionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # When: 本文を送信する
    try:
        status, body = HttpRecognitionConnection().request(
            f"http://127.0.0.1:{server.server_port}/v1/recognize",
            {"Authorization": "Bearer dummy"},
            b"audio",
            RecognitionParams(receive_timeout=1000),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    # Then: チャンクを結合しBearerをヘッダだけで送る
    assert status == 200
    assert body == b'{"text":"hello","code":"","message":""}'
    assert _RecognitionHandler.received == [("Bearer dummy", b"audio")]


def test_http_request_failure_invalid_raise_ConnectionFailedError() -> None:
    """接続例外に秘密情報を含めない"""
    # Given: OS例外を返すHTTP接続
    # When / Then: 安全な接続例外に変換する
    with (
        patch("http.client.HTTPSConnection.connect", side_effect=OSError("secret")),
        pytest.raises(ConnectionFailedError, match=r"^HTTP recognition connection failed$"),
    ):
        HttpRecognitionConnection().request("https://example.test/v1/recognize", {}, b"", RecognitionParams())
