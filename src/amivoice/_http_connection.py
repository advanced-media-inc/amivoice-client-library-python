"""標準ライブラリの HTTP 接続設定（TLS 検証、プロキシ、CONNECT）"""

import base64
import http.client
from urllib.parse import unquote, urlsplit

from .exceptions import ConfigurationError


def create_http_connection(
    url: str, *, connect_timeout_ms: int = 0, proxy_server_name: str | None = None, websocket: bool = False
) -> tuple[http.client.HTTPConnection, str]:
    """HTTP 接続とリクエストターゲットを返す（接続はまだ開かない）

    Args:
        url (str): 接続先の絶対 URL
        connect_timeout_ms (int): 接続タイムアウト、0 は無制限
        proxy_server_name (str | None): 任意の user:password@host:port 形式 HTTP プロキシ
        websocket (bool): WebSocket の ws / wss URL と CONNECT を許可する

    Returns:
        tuple[http.client.HTTPConnection, str]: 接続とパスまたは絶対 URL

    Raises:
        ConfigurationError: URL やプロキシが不正な場合
    """
    try:
        parsed = urlsplit(url)
        allowed = {"ws", "wss"} if websocket else {"http", "https"}
        if parsed.scheme not in allowed or not parsed.hostname or parsed.username is not None or parsed.fragment:
            raise ValueError("invalid endpoint")
        secure = parsed.scheme in {"https", "wss"}
        origin_port = parsed.port or (443 if secure else 80)
        host, port = parsed.hostname, origin_port
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        proxy_headers: dict[str, str] = {}
        if proxy_server_name:
            proxy = urlsplit(proxy_server_name if "://" in proxy_server_name else "http://" + proxy_server_name)
            if proxy.scheme != "http" or not proxy.hostname or proxy.path not in {"", "/"} or proxy.query or proxy.fragment:
                raise ValueError("invalid proxy")
            host, port = proxy.hostname, proxy.port or 80
            if proxy.username is not None:
                credentials = f"{unquote(proxy.username)}:{unquote(proxy.password or '')}"
                proxy_headers["Proxy-Authorization"] = "Basic " + base64.b64encode(credentials.encode()).decode("ascii")
    except ValueError as exc:
        # URL / プロキシの認証情報を例外メッセージへ出さない
        raise ConfigurationError("Invalid recognition endpoint or HTTP proxy") from exc
    connection_type = http.client.HTTPSConnection if secure else http.client.HTTPConnection
    connection = connection_type(host, port, timeout=connect_timeout_ms / 1000 if connect_timeout_ms > 0 else None)
    if proxy_server_name:
        # HTTP もトンネルにして、認証ヘッダーをオリジンから隔離する
        connection.set_tunnel(parsed.hostname, origin_port, headers=proxy_headers)
    return connection, target
