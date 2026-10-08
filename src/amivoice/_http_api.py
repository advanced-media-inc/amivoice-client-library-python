"""辞書・APIキー・感情パラメータAPIで使うHTTPS通信"""

import http.client
import math
import ssl
from urllib.parse import urlsplit

from ._connection_settings import parse_service_url
from ._user_agent import build_client_user_agent
from .exceptions import AuthenticationError, ConfigurationError


def validate_service_api_key(value: object) -> str:
    """認証情報の未指定とHTTPヘッダへの制御文字混入を拒否する

    Args:
        value (object): APIキー候補

    Returns:
        str: 検証済みの認証情報

    Raises:
        AuthenticationError: 指定されていない場合
        ConfigurationError: 文字列以外又は制御文字を含む場合
    """
    if value is None or value == "":
        raise AuthenticationError("API key is required")
    if not isinstance(value, str) or not value.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise ConfigurationError("api_key must not contain whitespace or control characters")
    return value


class HttpApiConnection:
    """1回のHTTPSリクエストが終わるたびに接続を閉じる"""

    def __init__(self, timeout: float) -> None:
        """秒単位の待機時間を保持する

        Args:
            timeout (float): 接続と受信のタイムアウト

        Raises:
            ConfigurationError: タイムアウトが不正な場合
        """
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
            raise ConfigurationError("API timeout must be a finite positive number")
        self._timeout = timeout

    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        """本文とHTTPステータスを取得する

        Args:
            method (str): HTTPメソッド
            url (str): adfなどの公式クエリを含むURL
            headers (dict[str, str]): 認証とContent-Type
            body (bytes | None): リクエスト本文

        Returns:
            tuple[int, bytes]: ステータスとレスポンス本文
        """
        parsed = urlsplit(url)
        parse_service_url(parsed._replace(query="").geturl(), ("https",))
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        # Python 3.11以降で証明書検証・ホスト名照合を有効にしたSSLContextを使う
        # nosemgrep: python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
        connection = http.client.HTTPSConnection(parsed.netloc, timeout=self._timeout, context=ssl.create_default_context())
        try:
            connection.request(method, target, body=body, headers={"User-Agent": build_client_user_agent(), **headers})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()
