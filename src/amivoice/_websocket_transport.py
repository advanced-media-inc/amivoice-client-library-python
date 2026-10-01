"""標準ライブラリのみで実装する RFC 6455 WebSocket 通信

AmiVoice 電文や認識状態は扱わない。HTTP ハンドシェイク、TLS、CONNECT は
http.client に委譲し、標準ライブラリにないフレーム処理だけをここで実装する
"""

import base64
import hashlib
import http.client
import secrets
import socket
import struct
import threading
from contextlib import suppress
from typing import BinaryIO

from ._http_connection import create_http_connection
from .exceptions import AuthenticationError, ConnectionFailedError, RecognitionError

_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
_MAX_MESSAGE_BYTES = 16 * 1024 * 1024


class WebSocketTransport:
    """一つの接続を所有する汎用 WebSocket クライアント（読み手は一スレッド）"""

    def __init__(self) -> None:
        """接続状態とフレーム送信ロックを初期化する"""
        self._connection: http.client.HTTPConnection | None = None
        self._socket: socket.socket | None = None
        self._reader: BinaryIO | None = None
        self._response: http.client.HTTPResponse | None = None
        self._send_lock = threading.Lock()
        self._close_sent = False

    def connect(
        self, api_url: str, *, connect_timeout_ms: int = 0, receive_timeout_ms: int = 0, proxy_server_name: str | None = None
    ) -> None:
        """HTTP Upgrade を検証して WebSocket 接続を開く

        Args:
            api_url (str): ws / wss の絶対 URL
            connect_timeout_ms (int): TCP / TLS 接続タイムアウト、0 は無制限
            receive_timeout_ms (int): 受信タイムアウト、0 は無制限
            proxy_server_name (str | None): HTTP プロキシ設定

        Raises:
            ConnectionFailedError: 接続または Upgrade 検証失敗
            AuthenticationError: HTTP 401 / 403
        """
        if self._socket is not None:
            raise ConnectionFailedError("WebSocket is already connected")
        connection, target = create_http_connection(
            api_url, connect_timeout_ms=connect_timeout_ms, proxy_server_name=proxy_server_name, websocket=True
        )
        self._connection = connection
        self._close_sent = False
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        try:
            connection.connect()
            self._socket = connection.sock
            if self._socket is None:
                raise ConnectionFailedError("WebSocket connection has no socket")
            self._socket.settimeout(receive_timeout_ms / 1000 if receive_timeout_ms > 0 else None)
            connection.putrequest("GET", target, skip_accept_encoding=True)
            for name, value in {
                "Upgrade": "websocket",
                "Connection": "Upgrade",
                "Sec-WebSocket-Key": key,
                "Sec-WebSocket-Version": "13",
            }.items():
                connection.putheader(name, value)
            connection.endheaders()
            # getresponse() は 101 を通常の HTTP 応答として close する場合がある
            # HTTPResponse のバッファをそのまま引き継ぎ、同時到着したフレームを失わない
            response = http.client.HTTPResponse(self._socket)
            self._response = response
            self._reader = response.fp
            response.begin()
            if response.status in {401, 403}:
                raise AuthenticationError(f"WebSocket authentication failed: HTTP {response.status}")
            # RFC 6455 §4.2.2 は SHA-1 を指定する（署名や認証には使用しない）
            # nosemgrep: python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
            expected = base64.b64encode(hashlib.sha1((key + _WEBSOCKET_GUID).encode(), usedforsecurity=False).digest()).decode()
            tokens = {token.strip().lower() for token in response.headers.get("Connection", "").split(",")}
            if (
                response.status != 101
                or response.headers.get("Upgrade", "").lower() != "websocket"
                or "upgrade" not in tokens
                or response.headers.get("Sec-WebSocket-Accept") != expected
            ):
                raise ConnectionFailedError("Invalid WebSocket upgrade response")
            if response.headers.get("Sec-WebSocket-Extensions") or response.headers.get("Sec-WebSocket-Protocol"):
                raise ConnectionFailedError("Unsupported WebSocket upgrade negotiation")
        except (OSError, http.client.HTTPException) as exc:
            self.close()
            raise ConnectionFailedError("WebSocket connection failed") from exc
        except BaseException:
            self.close()
            raise

    def send_text(self, message: str) -> None:
        """UTF-8 テキストメッセージをマスク付きで送信する

        Args:
            message (str): メッセージ本文
        """
        self._send_frame(message.encode("UTF-8"), 1)

    def send_binary(self, payload: bytes) -> None:
        """バイナリメッセージをマスク付きで送信する

        Args:
            payload (bytes): メッセージ本文
        """
        self._send_frame(payload, 2)

    def _send_frame(self, payload: bytes, opcode: int) -> None:
        with self._send_lock:
            if self._socket is None:
                raise RecognitionError("WebSocket is not connected")
            size = len(payload)
            header = bytes([0x80 | opcode])
            if size < 126:
                header += bytes([0x80 | size])
            elif size < 65536:
                header += b"\xfe" + struct.pack("!H", size)
            else:
                header += b"\xff" + struct.pack("!Q", size)
            mask = secrets.token_bytes(4)
            encoded = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
            try:
                self._socket.sendall(header + mask + encoded)
            except OSError as exc:
                raise RecognitionError("WebSocket send failed") from exc

    def _read_exact(self, size: int) -> bytes:
        if self._reader is None:
            raise RecognitionError("WebSocket is not connected")
        data = bytearray()
        while len(data) < size:
            chunk = self._reader.read(size - len(data))
            if not chunk:
                raise RecognitionError("WebSocket closed before message completed")
            data.extend(chunk)
        return bytes(data)

    def _read_frame(self) -> tuple[bool, int, bytes]:
        first, second = self._read_exact(2)
        final, opcode = bool(first & 0x80), first & 0x0F
        if first & 0x70 or second & 0x80 or opcode not in {0, 1, 2, 8, 9, 10}:
            raise RecognitionError("Invalid WebSocket frame flags")
        size = second & 0x7F
        if size == 126:
            size = struct.unpack("!H", self._read_exact(2))[0]
            if size < 126:
                raise RecognitionError("Invalid WebSocket frame length")
        elif size == 127:
            size = struct.unpack("!Q", self._read_exact(8))[0]
            if size < 65536 or size & (1 << 63):
                raise RecognitionError("Invalid WebSocket frame length")
        if opcode >= 8 and (not final or size > 125):
            raise RecognitionError("Invalid WebSocket control frame")
        if size > _MAX_MESSAGE_BYTES:
            raise RecognitionError("WebSocket message is too large")
        return final, opcode, self._read_exact(size)

    def _receive_close(self, payload: bytes) -> None:
        if len(payload) == 1:
            raise RecognitionError("Invalid WebSocket close payload")
        if len(payload) >= 2:
            code = struct.unpack("!H", payload[:2])[0]
            if code not in {1000, 1001, 1002, 1003, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014} and not 3000 <= code < 5000:
                raise RecognitionError("Invalid WebSocket close code")
            payload[2:].decode("UTF-8")
        if not self._close_sent:
            self._send_frame(payload, 8)
            self._close_sent = True
        raise RecognitionError("WebSocket closed by server")

    def receive_message(self) -> str | bytes:
        """分割フレームを再構成し、Ping には自動で Pong を返す

        Returns:
            str | bytes: テキストまたはバイナリメッセージ

        Raises:
            RecognitionError: EOF、タイムアウト、不正フレーム、接続終了
        """
        fragments = bytearray()
        message_opcode: int | None = None
        try:
            while True:
                final, opcode, payload = self._read_frame()
                if opcode == 8:
                    self._receive_close(payload)
                if opcode == 9:
                    self._send_frame(payload, 10)
                    continue
                if opcode == 10:
                    continue
                if opcode == 0:
                    if message_opcode is None:
                        raise RecognitionError("Unexpected WebSocket continuation")
                elif message_opcode is not None:
                    raise RecognitionError("Interrupted WebSocket fragmented message")
                else:
                    message_opcode = opcode
                if len(fragments) + len(payload) > _MAX_MESSAGE_BYTES:
                    raise RecognitionError("WebSocket message is too large")
                fragments.extend(payload)
                if final:
                    return fragments.decode("UTF-8") if message_opcode == 1 else bytes(fragments)
        except (OSError, ValueError) as exc:
            raise RecognitionError("WebSocket receive failed") from exc

    def close(self) -> None:
        """ソケットを shutdown して受信待機を解除し、全リソースを閉じる"""
        if self._socket is not None:
            # 受信スレッドが BufferedReader.read() 中でも close() がデッドロックしない
            with suppress(OSError):
                self._socket.shutdown(socket.SHUT_RDWR)
            self._socket.close()
            self._socket = None
        if self._response is not None:
            self._response.close()
            self._response = None
        elif self._reader is not None:
            self._reader.close()
        self._reader = None
        if self._connection is not None:
            self._connection.close()
            self._connection = None
