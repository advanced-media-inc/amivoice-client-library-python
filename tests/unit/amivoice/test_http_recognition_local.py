"""実際のローカル HTTP サーバーとの HRP 通信テスト（認証情報は不要）"""

import threading
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from amivoice import transcribe


class _RecognitionHandler(BaseHTTPRequestHandler):
    """チャンク送信を記録しチャンク応答を返すテストサーバー"""

    audio: bytes = b""
    path_received: str = ""

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
        self.send_header("Content-Type", "application/json; charset=Shift_JIS")
        self.send_header("X-Session-ID", "local-session")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        data = '{"text":"日本語"}\r\n'.encode("shift_jis")
        # JSON とマルチバイト文字が HTTP チャンク境界をまたぐ
        for offset in range(0, len(data), 3):
            chunk = data[offset : offset + 3]
            self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
        self.wfile.write(b"0\r\n\r\n")

    def log_message(self, format: str, *args: object) -> None:
        """テスト用 HTTP アクセスログを抑止する"""


def test_transcribe_local_server_valid_return_chunked_result() -> None:
    """公開 API から実 HTTP チャンク送受信と文字コード解決を検証する"""
    # Given: 認証不要のループバックサーバー
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RecognitionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    audio = bytes(range(256)) * 50
    try:
        # When: 公開 API で認識する
        result = transcribe(
            audio, api_key="test", api_url=f"http://127.0.0.1:{server.server_port}/recognize?x=1", receive_timeout=1000
        )
        # Then: 本文、文字コード、session ID を保持する
        assert _RecognitionHandler.audio == audio
        assert _RecognitionHandler.path_received == "/recognize?x=1"
        assert result.text == "日本語"
        assert result.session_id == "local-session"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
