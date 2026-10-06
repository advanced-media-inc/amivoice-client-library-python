"""通信先URLとHTTPプロキシの設定を検証する"""

import base64
from urllib.parse import SplitResult, urlsplit

from .exceptions import ConfigurationError


def parse_service_url(url: str, schemes: tuple[str, ...]) -> SplitResult:
    """認証情報やクエリを含まない接続先を解析する

    Args:
        url (str): 接続先URL
        schemes (tuple[str, ...]): 許可するスキーム

    Returns:
        SplitResult: 解析済みのURL

    Raises:
        ConfigurationError: URLの形式が不正な場合
    """
    if not isinstance(url, str) or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        raise ConfigurationError("Service URL must not contain whitespace or control characters")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ConfigurationError("Service URL has an invalid host or port") from None
    if parsed.scheme not in schemes or not parsed.hostname or parsed.username is not None or parsed.query or parsed.fragment:
        raise ConfigurationError("Service URL must be absolute and contain no credentials, query or fragment")
    if port is not None and not 1 <= port <= 65535:
        raise ConfigurationError("Service URL port must be between 1 and 65535")
    return parsed


def parse_http_proxy(value: str | None) -> tuple[str, int, dict[str, str]] | None:
    """HTTP CONNECTに使うプロキシと認証ヘッダを返す

    Args:
        value (str | None): host:portまたはhttp://user:password@host:port

    Returns:
        tuple[str, int, dict[str, str]] | None: ホスト、ポート、プロキシ認証ヘッダ

    Raises:
        ConfigurationError: HTTP以外のスキームや不正な指定を含む場合
    """
    if value is None:
        return None
    if not isinstance(value, str) or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ConfigurationError("HTTP proxy must not contain whitespace or control characters")
    try:
        parsed = urlsplit(value if "://" in value else "http://" + value)
        port = parsed.port or 80
    except ValueError:
        raise ConfigurationError("HTTP proxy has an invalid host or port") from None
    if parsed.scheme != "http" or not parsed.hostname or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ConfigurationError("HTTP proxy must use an HTTP host and port")
    headers = {}
    if parsed.username is not None:
        credentials = f"{parsed.username}:{parsed.password or ''}".encode()
        headers["Proxy-Authorization"] = "Basic " + base64.b64encode(credentials).decode("ascii")
    return parsed.hostname, port, headers
