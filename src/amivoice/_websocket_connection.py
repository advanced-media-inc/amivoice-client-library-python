"""RFC 6455の接続・マスク・分割フレーム・Ping/Pong処理"""

import base64
import hashlib
import secrets
import socket
import ssl
import struct
import threading
from contextlib import suppress
from typing import Protocol

from ._connection_settings import parse_http_proxy, parse_service_url
from ._params import RecognitionParams
from ._user_agent import build_client_user_agent
from .exceptions import ConfigurationError, ConnectionFailedError, RecognitionError

_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_MAX_MESSAGE_BYTES = 16 * 1024 * 1024  # ローカルの受信メモリ上限
_MAX_HEADER_BYTES = 65536


class WebSocketTransport(Protocol):
    """開始コマンドと認識イベントに使うテキスト通信のインタフェース"""

    def connect(self, url: str, api_key: str, params: RecognitionParams) -> None:
        """Bearer認証で接続する"""
        ...

    def send_text(self, text: str) -> None:
        """UTF-8テキストを送信する"""
        ...

    def send_audio(self, audio: bytes) -> None:
        """pの1バイトを先頭に付けて音声を送信する"""
        ...

    def receive_text(self) -> str | None:
        """テキストを受信し、切断時はNoneを返す"""
        ...

    def close(self) -> None:
        """接続を閉じ受信待機を解除する"""
        ...


class WebSocketConnection:
    """標準ライブラリでWebSocketを処理する、1接続につき受信者は1つ"""

    def __init__(self) -> None:
        """接続と送信ロックを初期化する"""
        self._socket: socket.socket | None = None
        self._buffer = bytearray()
        self._send_lock = threading.Lock()

    def connect(self, url: str, api_key: str, params: RecognitionParams) -> None:
        """Upgrade応答を検証し、受信タイムアウトを適用する

        Args:
            url (str): wsまたはwssの接続先
            api_key (str): Bearer認証情報
            params (RecognitionParams): ミリ秒単位の通信設定

        Raises:
            ConnectionFailedError: 接続やハンドシェイクに失敗した場合
            ConfigurationError: 二重接続や不正な設定の場合
        """
        if self._socket is not None:
            raise ConfigurationError("WebSocket connection is already open")
        parsed = parse_service_url(url, ("wss", "ws"))
        proxy = parse_http_proxy(params.proxy_server_name)
        if not api_key or any(ord(c) < 32 or ord(c) == 127 for c in api_key):
            raise ConfigurationError("API key must not be empty or contain control characters")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        target = (parsed.hostname, port)
        address = (proxy[0], proxy[1]) if proxy else target
        user_agent = build_client_user_agent()
        try:
            self._socket = socket.create_connection(address, timeout=params.connect_timeout / 1000 or None)
            self._socket.settimeout(params.receive_timeout / 1000 or None)
            if proxy:
                host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
                authority = f"{host}:{port}"
                lines = [f"CONNECT {authority} HTTP/1.1", f"Host: {authority}", f"User-Agent: {user_agent}"]
                lines.extend(f"{key}: {value}" for key, value in proxy[2].items())
                self._socket.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("ascii"))
                status, _ = self._read_http_headers(allow_http_10=True)
                if status != 200 or self._buffer:
                    raise ConnectionFailedError("WebSocket proxy tunnel failed")
            if parsed.scheme == "wss":
                self._socket = ssl.create_default_context().wrap_socket(self._socket, server_hostname=parsed.hostname)
            key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
            request = "\r\n".join(
                [
                    f"GET {parsed.path or '/'} HTTP/1.1",
                    f"Host: {parsed.netloc}",
                    f"User-Agent: {user_agent}",
                    "Upgrade: websocket",
                    "Connection: Upgrade",
                    f"Sec-WebSocket-Key: {key}",
                    "Sec-WebSocket-Version: 13",
                    f"Authorization: Bearer {api_key}",
                    "",
                    "",
                ]
            )
            self._socket.sendall(request.encode("utf-8"))
            status, headers = self._read_http_headers()
            # RFC 6455 §4.2.2で必須のSHA-1、署名用途ではない
            # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
            digest = hashlib.sha1((key + _WEBSOCKET_GUID).encode("ascii"), usedforsecurity=False).digest()
            expected = base64.b64encode(digest).decode("ascii")
            if (
                status != 101
                or ", ".join(headers.get("upgrade", [])).lower() != "websocket"
                or "upgrade" not in [token.strip().lower() for token in ", ".join(headers.get("connection", [])).split(",")]
                # RFC 6455 §11.3.3: Acceptは応答に1つだけ必要
                or headers.get("sec-websocket-accept") != [expected]
            ):
                raise ConnectionFailedError("WebSocket upgrade response is invalid")
        except (OSError, ValueError, ConnectionFailedError):
            self.close()
            raise ConnectionFailedError("WebSocket connection or upgrade failed") from None

    def _read_http_headers(self, *, allow_http_10: bool = False) -> tuple[int, dict[str, list[str]]]:
        """CONNECTだけHTTP/1.0を許容し、Set-Cookieを含む重複値を個別に保持する

        Args:
            allow_http_10 (bool): プロキシのCONNECT応答でHTTP/1.0も受理するか

        Returns:
            tuple[int, dict[str, list[str]]]: ステータスと受信順のヘッダ値
        """
        while b"\r\n\r\n" not in self._buffer:
            if len(self._buffer) > _MAX_HEADER_BYTES:
                raise ConnectionFailedError("WebSocket HTTP headers are too large")
            data = self._socket.recv(4096)
            if not data:
                raise ConnectionFailedError("WebSocket upgrade ended before HTTP headers")
            self._buffer.extend(data)
        head, _, remaining = self._buffer.partition(b"\r\n\r\n")
        if len(head) > _MAX_HEADER_BYTES:
            raise ConnectionFailedError("WebSocket HTTP headers are too large")
        self._buffer = bytearray(remaining)
        lines = head.decode("iso-8859-1").split("\r\n")
        status_line = lines[0].split()
        allowed_versions = ("HTTP/1.0", "HTTP/1.1") if allow_http_10 else ("HTTP/1.1",)
        if len(status_line) < 2 or status_line[0] not in allowed_versions:
            raise ConnectionFailedError("WebSocket HTTP status line is invalid")
        headers: dict[str, list[str]] = {}
        for line in lines[1:]:
            name, separator, value = line.partition(":")
            name = name.lower()
            if not separator:
                raise ConnectionFailedError("WebSocket HTTP response headers are invalid")
            headers.setdefault(name, []).append(value.strip())
        return int(status_line[1]), headers

    def _read_exact(self, length: int) -> bytes | None:
        while len(self._buffer) < length:
            sock = self._socket
            if sock is None:
                return None
            data = sock.recv(min(length - len(self._buffer), 65536))
            if not data:
                if self._buffer:
                    raise RecognitionError("WebSocket frame is truncated")
                return None
            self._buffer.extend(data)
        data = bytes(self._buffer[:length])
        del self._buffer[:length]
        return data

    def _require_bytes(self, length: int) -> bytes:
        data = self._read_exact(length)
        if data is None:
            raise RecognitionError("WebSocket frame is truncated")
        return data

    def _receive_frame(self) -> tuple[bool, int, bytes] | None:
        head = self._read_exact(2)
        if head is None:
            return None
        fin, opcode = bool(head[0] & 0x80), head[0] & 0x0F
        if head[0] & 0x70 or head[1] & 0x80 or opcode not in (0, 1, 8, 9, 10):
            raise RecognitionError("WebSocket server frame flags or opcode are invalid")
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._require_bytes(2))[0]
            if length < 126:
                raise RecognitionError("WebSocket frame length is not canonical")
        elif length == 127:
            length = struct.unpack("!Q", self._require_bytes(8))[0]
            if length < 65536 or length >= 1 << 63:
                raise RecognitionError("WebSocket frame length is invalid")
        if length > _MAX_MESSAGE_BYTES or (opcode >= 8 and (not fin or length > 125)):
            raise RecognitionError("WebSocket frame size or control fragmentation is invalid")
        return fin, opcode, self._require_bytes(length)

    def receive_text(self) -> str | None:
        """分割UTF-8を再構成し、PingにPongを返す

        Returns:
            str | None: 完全なテキスト、切断時はNone

        Raises:
            RecognitionError: フレームが不正な場合や通信に失敗した場合
        """
        message = bytearray()
        fragmented = False
        try:
            while True:
                frame = self._receive_frame()
                if frame is None:
                    if fragmented:
                        raise RecognitionError("WebSocket fragmented message is truncated")
                    return None
                fin, opcode, payload = frame
                if opcode >= 8:
                    if self._handle_control(opcode, payload, fragmented):
                        return None
                    continue
                if (opcode == 0 and not fragmented) or (opcode == 1 and fragmented):
                    raise RecognitionError("WebSocket continuation order is invalid")
                message.extend(payload)
                if len(message) > _MAX_MESSAGE_BYTES:
                    raise RecognitionError("WebSocket message exceeds the local memory limit")
                if fin:
                    return message.decode("utf-8")
                fragmented = True
        except (OSError, UnicodeDecodeError):
            raise RecognitionError("WebSocket receive failed or text is not UTF-8") from None

    def _handle_control(self, opcode: int, payload: bytes, fragmented: bool) -> bool:
        if opcode == 9:
            self._send_frame(10, payload)
        elif opcode == 8:
            if len(payload) == 1:
                raise RecognitionError("WebSocket close payload is invalid")
            if len(payload) >= 2:
                payload[2:].decode("utf-8")
            self._send_frame(8, payload)
            if fragmented:
                raise RecognitionError("WebSocket closed during a fragmented message")
            return True
        return False

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        length = len(payload)
        if length < 126:
            header = bytes((0x80 | opcode, 0x80 | length))
        elif length < 65536:
            header = bytes((0x80 | opcode, 0xFE)) + struct.pack("!H", length)
        else:
            header = bytes((0x80 | opcode, 0xFF)) + struct.pack("!Q", length)
        mask = secrets.token_bytes(4)
        masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
        with self._send_lock:
            if self._socket is None:
                raise RecognitionError("WebSocket connection is closed")
            try:
                self._socket.sendall(header + mask + masked)
            except OSError:
                raise RecognitionError("WebSocket send failed") from None

    def send_text(self, text: str) -> None:
        """開始と終了のテキストをマスクして送信する

        Args:
            text (str): コマンド文字列
        """
        self._send_frame(1, text.encode("utf-8"))

    def send_audio(self, audio: bytes) -> None:
        """pの1バイトを音声の先頭に付けマスクして送る

        Args:
            audio (bytes): 音声データ
        """
        self._send_frame(2, b"p" + audio)

    def close(self) -> None:
        """ソケットを閉じ、他スレッドの受信待機を解除する"""
        sock, self._socket = self._socket, None
        if sock is not None:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            sock.close()
        self._buffer.clear()
