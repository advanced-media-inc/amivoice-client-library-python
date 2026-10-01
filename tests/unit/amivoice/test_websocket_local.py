"""ループバックサーバーとの WebSocket / WRP 結合テスト"""

import base64
import hashlib
import struct
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

import pytest

from amivoice import AmiVoiceClient
from amivoice._websocket_transport import WebSocketTransport
from amivoice.exceptions import AuthenticationError, ConnectionFailedError, RecognitionError


class _WebSocketHandler(BaseHTTPRequestHandler):
    """HTTP Upgrade と認識コマンドを実際に処理するサーバー"""

    start_command: str = ""
    audio: bytes = b""

    def _send_frame(self, payload: bytes, opcode: int = 1, *, final: bool = True) -> None:
        self.wfile.write(bytes([(128 if final else 0) | opcode, len(payload)]) + payload)
        self.wfile.flush()

    def _receive_frame(self) -> tuple[int, bytes]:
        first, second = self.rfile.read(2)
        assert second & 128
        size = second & 127
        if size == 126:
            size = struct.unpack("!H", self.rfile.read(2))[0]
        elif size == 127:
            size = struct.unpack("!Q", self.rfile.read(8))[0]
        mask = self.rfile.read(4)
        return first & 15, bytes(value ^ mask[index % 4] for index, value in enumerate(self.rfile.read(size)))

    def do_GET(self) -> None:
        """ハンドシェイクと複数の異常応答を提供する"""
        self.connection.settimeout(2)
        if self.path == "/unauthorized":
            self.send_error(401)
            return
        key = self.headers["Sec-WebSocket-Key"]
        # RFC 6455 の Upgrade 応答を生成するためだけに SHA-1 を使用する
        # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
        digest = hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(), usedforsecurity=False).digest()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "keep-alive, Upgrade")
        self.send_header("Sec-WebSocket-Accept", "wrong" if self.path == "/bad-accept" else base64.b64encode(digest).decode())
        self.end_headers()
        if self.path == "/bad-accept":
            return
        if self.path == "/coalesced":
            # Upgrade と同時到着したフレームをバッファから引き継ぐ
            self._send_frame(b"coalesced")
            return
        opcode, start = self._receive_frame()
        assert opcode == 1
        type(self).start_command = start.decode()
        if self.path == "/no-start-ack":
            self.rfile.read(1)  # クライアントの close() が受信待機を解除する
            return
        self._send_frame(b"s")
        self._send_frame(b"Q ready")
        if self.path == "/broken-json":
            self._send_frame(b"A broken")
            return
        opcode, audio = self._receive_frame()
        assert opcode == 2
        assert audio.startswith(b"p")
        type(self).audio = audio[1:]
        self._send_frame(b"S 100")
        if self.path == "/recognition-after-end":
            self._send_frame(b"E 500")
        self._send_frame(b"C")
        self._send_frame(b"U partial")
        if self.path != "/recognition-after-end":
            self._send_frame(b"E 500")
        opcode, end = self._receive_frame()
        assert opcode == 1 and end == b"e"
        # e 確認の後に確定結果が来ても end() は待ち続ける
        self._send_frame(b"e")
        data = 'A {"text":"日本語"}'.encode()
        self._send_frame(data[:15], final=False)
        self._send_frame(b"ping", opcode=9)
        self._send_frame(data[15:], opcode=0)
        opcode, pong = self._receive_frame()
        assert opcode == 10 and pong == b"ping"

    def log_message(self, format: str, *args: object) -> None:
        """テスト用アクセスログを抑止する"""


@contextmanager
def _websocket_server() -> Iterator[str]:
    """ローカルサーバーの接続先 URL を返し、必ず停止する"""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _WebSocketHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"ws://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("recognition_after_end", [False, True])
@pytest.mark.parametrize("consume", ["events", "poll"])
def test_stream_local_server_valid_return_events_and_audio(recognition_after_end: bool, consume: str) -> None:
    """公開 API から認識処理開始の受信順と分割メッセージを検証する"""
    # Given: 実 WebSocket 接続と大きな音声チャンク
    audio = b"x" * 65536
    with _websocket_server() as url:
        path = "/recognition-after-end" if recognition_after_end else "/"
        client = AmiVoiceClient(api_key="test", ws_api_url=url + path, receive_timeout=2000)
        # When: 開始、音声送信、終了を行う
        with client.stream(profile_id=":profile", codec="LSB16K") as session:
            session.write(audio)
            session.end(timeout=1)
            events = list(getattr(session, consume)())
            results = session.results()
        # Then: C が発話終了の前後どちらでも受信順を維持し、未確定結果数を増やさない
        expected_types = ["notification", "utterance_started"]
        if recognition_after_end:
            expected_types += ["utterance_ended", "recognition_started", "partial"]
        else:
            expected_types += ["recognition_started", "partial", "utterance_ended"]
        assert [event.type for event in events] == [*expected_types, "final"]
        assert len(results) == 1
        assert results[0].text == "日本語"
        assert _WebSocketHandler.audio == audio
        assert "profileId=:profile" in _WebSocketHandler.start_command
        assert _WebSocketHandler.start_command.startswith("s LSB16K ")
        assert not session._receiver.is_alive()
        # events / poll の終端を消費した後も再度無期限待機しない
        assert list(session.events()) == []
        assert list(session.poll()) == []


@pytest.mark.parametrize(("path", "error"), [("/unauthorized", AuthenticationError), ("/bad-accept", ConnectionFailedError)])
def test_websocket_upgrade_invalid_raise_public_error(path: str, error: type[Exception]) -> None:
    """認証エラーと Sec-WebSocket-Accept 検証失敗を公開例外にする"""
    # Given: 不正なハンドシェイクのサーバー
    with _websocket_server() as url:
        transport = WebSocketTransport()
        # When / Then: 接続失敗でもソケットを保持しない
        with pytest.raises(error):
            transport.connect(url + path, connect_timeout_ms=1000, receive_timeout_ms=1000)
        assert transport._socket is None
        assert transport._reader is None


def test_websocket_coalesced_frame_valid_return_first_message() -> None:
    """HTTP 応答バッファ内の最初のフレームを失わない"""
    # Given: Upgrade 直後に送信するサーバー
    with _websocket_server() as url:
        transport = WebSocketTransport()
        try:
            # When: Upgrade 後の最初のフレームを読み取る
            transport.connect(url + "/coalesced", receive_timeout_ms=1000)
            message = transport.receive_message()
            # Then: HTTPResponse のバッファ内のフレームも返る
            assert message == "coalesced"
        finally:
            transport.close()


def test_stream_start_timeout_invalid_raise_RecognitionError() -> None:
    """受信タイムアウト未設定でも開始確認の期限と後始末を保証する"""
    # Given: 開始確認を返さない接続
    with _websocket_server() as url:
        client = AmiVoiceClient(api_key="test", ws_api_url=url + "/no-start-ack", receive_timeout=30)
        # When / Then: 待機をタイムアウトして receiver を残さない
        with pytest.raises(RecognitionError), client.stream():
            pass


def test_stream_receiver_failure_invalid_raise_RecognitionError() -> None:
    """バックグラウンドの JSON エラーをイベント利用者へ伝播する"""
    # Given: 開始直後に不正な結果を送るサーバー
    with _websocket_server() as url:
        client = AmiVoiceClient(api_key="test", ws_api_url=url + "/broken-json", receive_timeout=1000)
        # When / Then: 開始またはイベント受信で例外が届く
        with pytest.raises(RecognitionError), client.stream() as session:
            list(session.events(timeout=1))
