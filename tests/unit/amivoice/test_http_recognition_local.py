"""実際のローカル HTTP サーバーとの HRP 通信テスト（認証情報は不要）"""

import json
import threading
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from amivoice import transcribe


class _RecognitionHandler(BaseHTTPRequestHandler):
    """チャンク送信を記録しチャンク応答を返すテストサーバー"""

    audio: bytes = b""
    path_received: str = ""
    escape_unicode: bool = True

    def do_POST(self) -> None:
        """HTTP チャンクを受け取り認識応答を送る"""
        assert self.headers["Transfer-Encoding"] == "chunked"
        body = bytearray()
        while size := int(self.rfile.readline().strip(), 16):
            body.extend(self.rfile.read(size))
            assert self.rfile.read(2) == b"\r\n"
        assert self.rfile.readline() == b"\r\n"
        mime = BytesParser().parsebytes(f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body)
        type(self).audio = next(
            part.get_payload(decode=True)
            for part in mime.get_payload()
            if part.get_param("name", header="content-disposition") == "a"
        )
        type(self).path_received = self.path
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=UTF-8")
        self.send_header("X-Session-ID", "local-session")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        data = (json.dumps({"text": "髙﨑①"}, ensure_ascii=self.escape_unicode) + "\r\n").encode("utf-8")
        # HTTP チャンク境界をまたぐ JSON と UTF-8 のマルチバイト文字を検証する
        for offset in range(0, len(data), 3):
            chunk = data[offset : offset + 3]
            self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")

    def log_message(self, format: str, *args: object) -> None:
        """テスト用 HTTP アクセスログを抑止する"""


@pytest.mark.parametrize("escape_unicode", [True, False])
def test_transcribe_local_server_utf8_valid_return_chunked_result(escape_unicode: bool) -> None:
    """公開 API から UTF-8 の JSON 応答と実 HTTP チャンク送受信を検証する"""

    # Given: 認証不要のループバックサーバー
    class RecognitionHandler(_RecognitionHandler):
        pass

    RecognitionHandler.escape_unicode = escape_unicode
    server = ThreadingHTTPServer(("127.0.0.1", 0), RecognitionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    audio = bytes(range(256)) * 50
    try:
        # When: 公開 API で認識する
        result = transcribe(
            audio, api_key="test", api_url=f"http://127.0.0.1:{server.server_port}/recognize?x=1", receive_timeout=1000
        )
        # Then: 本文、文字コード、session ID を保持する
        assert RecognitionHandler.audio == audio
        assert RecognitionHandler.path_received == "/recognize?x=1"
        assert result.text == "髙﨑①"
        assert result.session_id == "local-session"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
