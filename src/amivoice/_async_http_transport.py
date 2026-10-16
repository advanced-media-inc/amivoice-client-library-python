"""標準ライブラリの非同期HTTPジョブ用POST・GET通信"""

import http.client
import socket
import time
from contextlib import suppress
from threading import Timer
from typing import Protocol

from ._async_audio import MultipartUpload
from ._connection_settings import parse_http_proxy, parse_service_url
from ._params import RecognitionParams
from ._user_agent import build_client_user_agent
from .exceptions import ConnectionFailedError


def _timeout(milliseconds: int, deadline: float | None) -> float | None:
    configured = milliseconds / 1000 or None
    if deadline is None:
        return configured
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Async HTTP wait deadline expired")
    return min(configured, remaining) if configured is not None else remaining


def _interrupt(sock: socket.socket) -> None:
    with suppress(OSError):
        sock.shutdown(socket.SHUT_RDWR)


class _ConnectionDeadline:
    """TCP接続直後からCONNECT・TLS・送受信に同じ絶対期限を適用する"""

    def __init__(self, connection: http.client.HTTPConnection, deadline: float | None) -> None:
        self._deadline = deadline
        self._create_connection = connection._create_connection
        self._socket: socket.socket | None = None
        self._timer: Timer | None = None
        if deadline is not None:
            # HTTPConnectionの接続生成フックで、CONNECT応答の読み取りより前に監視する
            connection._create_connection = self._connect

    def _connect(self, address: tuple[str, int], timeout: float | None, source_address: tuple[str, int] | None) -> socket.socket:
        sock = self._create_connection(address, timeout, source_address)
        try:
            remaining = _timeout(0, self._deadline)
            # TLSによるsocketの置き換え後も同じTCP接続をshutdownできるよう複製する
            self._socket = sock.dup()
            self._timer = Timer(remaining, _interrupt, args=(self._socket,))
            self._timer.daemon = True
            self._timer.start()
            return sock
        except BaseException:
            sock.close()
            raise

    def close(self) -> None:
        """監視スレッドを終了して監視用ソケットだけを閉じる"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer.join()
        if self._socket is not None:
            self._socket.close()


class AsyncHttpTransport(Protocol):
    """テスト注入用のPOST・GET通信、deadlineはmonotonicの絶対時刻"""

    def request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: MultipartUpload | None,
        params: RecognitionParams,
        *,
        deadline: float | None = None,
    ) -> tuple[int, bytes]:
        """本文を読み切り独立した接続を閉じる

        Args:
            method (str): POST又はGET
            url (str): 接続先
            headers (dict[str, str]): Bearer認証等のヘッダ
            body (MultipartUpload | None): POSTの送信本文、GETはNone
            params (RecognitionParams): プロキシとミリ秒の通信待機時間
            deadline (float | None): waitの残り時間を制限する締め切り

        Returns:
            tuple[int, bytes]: HTTPステータスと元の応答
        """
        ...


class AsyncHttpConnection:
    """長さ既知の本文を分割送信し、wait中のソケット処理には締め切りを適用する"""

    @staticmethod
    def _connection(
        url: str, headers: dict[str, str], params: RecognitionParams, deadline: float | None
    ) -> tuple[http.client.HTTPConnection, str, dict[str, str]]:
        parsed = parse_service_url(url, ("https", "http"))
        proxy = parse_http_proxy(params.proxy_server_name)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        target = parsed.path or "/"
        request_headers = {"User-Agent": build_client_user_agent(), **headers}
        host = parsed.hostname
        tunnel = None
        if proxy is not None:
            host, proxy_port, proxy_headers = proxy
            if parsed.scheme == "https":
                tunnel = (parsed.hostname, port, {"User-Agent": build_client_user_agent(), **proxy_headers})
            else:
                target = url
                request_headers.update(proxy_headers)
            port = proxy_port
        connection = connection_type(host, port, timeout=_timeout(params.connect_timeout, deadline))
        if tunnel is not None:
            connection.set_tunnel(*tunnel[:2], headers=tunnel[2])
        return connection, target, request_headers

    def request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: MultipartUpload | None,
        params: RecognitionParams,
        *,
        deadline: float | None = None,
    ) -> tuple[int, bytes]:
        """接続、送信、受信を行いリダイレクト・再送は行わない

        Args:
            method (str): POST又はGET
            url (str): 検証済みの接続先
            headers (dict[str, str]): 認証等のヘッダ
            body (MultipartUpload | None): 送信本文
            params (RecognitionParams): 通信設定
            deadline (float | None): monotonicの待機締め切り

        Returns:
            tuple[int, bytes]: HTTPステータスとUTF-8応答

        Raises:
            ConnectionFailedError: ソケット通信に失敗した場合
            TimeoutError: 締め切りを過ぎた場合
        """
        connection, target, request_headers = self._connection(url, headers, params, deadline)
        guard = _ConnectionDeadline(connection, deadline)
        try:
            connection.connect()
            if connection.sock is not None:
                connection.sock.settimeout(_timeout(params.receive_timeout, deadline))
            connection.putrequest(method, target, skip_accept_encoding=True)
            if body is not None:
                request_headers["Content-Length"] = str(body.content_length)
                request_headers["Content-Type"] = body.content_type
            for name, value in request_headers.items():
                connection.putheader(name, value)
            connection.endheaders()
            if body is not None:
                for chunk in body.chunks():
                    connection.send(chunk)
            response = connection.getresponse()
            chunks = []
            while chunk := response.read(65536):
                chunks.append(chunk)
            # read(size)はContent-Lengthに満たないEOFでも例外を送出しない
            if response.length is not None and response.length > 0:
                raise http.client.IncompleteRead(b"".join(chunks), response.length)
            # 読み切った本文を事後の期限チェックで捨てず、呼び出し元へ渡す
            return response.status, b"".join(chunks)
        except (OSError, http.client.HTTPException):
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Async HTTP wait deadline expired") from None
            raise ConnectionFailedError("Async HTTP connection failed") from None
        finally:
            guard.close()
            connection.close()
