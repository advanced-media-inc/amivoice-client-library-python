"""標準ライブラリによる同期HTTP認識の通信処理"""

import http.client
from typing import Protocol

from ._connection_settings import parse_http_proxy, parse_service_url
from ._params import RecognitionParams
from .exceptions import ConnectionFailedError


class HttpRecognitionTransport(Protocol):
    """同期HTTPの注入インタフェース、各呼び出しで独立した接続を使う"""

    def request(self, url: str, headers: dict[str, str], body: bytes, params: RecognitionParams) -> tuple[int, bytes]:
        """HTTPステータスとレスポンス本文を返す

        Args:
            url (str): 接続先
            headers (dict[str, str]): 認証とContent-Type
            body (bytes): multipart本文
            params (RecognitionParams): ミリ秒単位の通信設定

        Returns:
            tuple[int, bytes]: ステータスと本文
        """
        ...


class HttpRecognitionConnection:
    """http.clientで認識リクエストを送信し、必ず接続を閉じる"""

    def request(self, url: str, headers: dict[str, str], body: bytes, params: RecognitionParams) -> tuple[int, bytes]:
        """接続後に受信タイムアウトへ切り替えてPOSTする

        Args:
            url (str): 同期HTTPエンドポイント
            headers (dict[str, str]): 認証とmultipart形式
            body (bytes): 送信する本文
            params (RecognitionParams): 接続と受信のタイムアウト、プロキシ

        Returns:
            tuple[int, bytes]: HTTPレスポンス

        Raises:
            ConnectionFailedError: 接続、送受信に失敗した場合
        """
        parsed = parse_service_url(url, ("https", "http"))
        proxy = parse_http_proxy(params.proxy_server_name)
        connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        target = parsed.path or "/"
        request_headers = dict(headers)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        tunnel = None
        if proxy is not None:
            host, proxy_port, proxy_headers = proxy
            if parsed.scheme == "https":
                tunnel = (parsed.hostname, port, proxy_headers)
            else:
                target = url
                request_headers.update(proxy_headers)
            port = proxy_port
        connection = connection_type(host, port, timeout=params.connect_timeout / 1000 or None)
        if tunnel is not None:
            connection.set_tunnel(tunnel[0], tunnel[1], headers=tunnel[2])
        try:
            connection.connect()
            if connection.sock is not None:
                connection.sock.settimeout(params.receive_timeout / 1000 or None)
            connection.request("POST", target, body=body, headers=request_headers)
            response = connection.getresponse()
            return response.status, response.read()
        except (OSError, http.client.HTTPException):
            # 接続例外にURLや認証情報を含めない
            raise ConnectionFailedError("HTTP recognition connection failed") from None
        finally:
            connection.close()
