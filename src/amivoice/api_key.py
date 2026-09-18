"""AmiVoice API キー発行 API の高レベルクライアント。"""

import http.client
import os
import ssl
from collections.abc import Sequence
from datetime import timedelta
from typing import NoReturn, Protocol
from urllib.parse import urlencode, urlsplit

from .exceptions import ApiKeyApiError, AuthenticationError, ConfigurationError, ConnectionFailedError

__all__ = ["ApiKeyClient", "ApiKeyTransport"]

_DEFAULT_BASE_URL = "https://acp-api.amivoice.com"
_ISSUE_API_PATH = "/issue_service_authorization"


class ApiKeyTransport(Protocol):
    """API キー発行 API への HTTP リクエストを実行するトランスポート。"""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        """HTTP レスポンスのステータスコードと本文を返す。

        Args:
            method: HTTP メソッド
            url: リクエスト URL
            headers: HTTP リクエストヘッダー
            body: HTTP リクエスト本文

        Returns:
            HTTP ステータスコードとレスポンス本文
        """
        ...


class _HttpApiKeyTransport:
    """標準ライブラリで実装した API キー発行 API トランスポート。"""

    def __init__(self, timeout: float) -> None:
        """HTTP 接続タイムアウトを保持する。

        Args:
            timeout: HTTP 接続のタイムアウト秒数
        """
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        """HTTP リクエストを送り、ステータスコードと本文を返す。

        Args:
            method: HTTP メソッド
            url: リクエスト URL
            headers: HTTP リクエストヘッダー
            body: HTTP リクエスト本文

        Returns:
            HTTP ステータスコードとレスポンス本文

        Raises:
            ConfigurationError: URL が絶対 HTTPS URL でない場合
        """
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigurationError("base_url must be an absolute HTTPS URL")

        connection_class = http.client.HTTPSConnection
        connection = connection_class(
            parsed.netloc,
            timeout=self._timeout,
            context=ssl.create_default_context(),
        )
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        try:
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()


def _response_body_text(body: bytes) -> str:
    """レスポンス本文を表示用の文字列へ変換する。"""
    return body.decode("utf-8", errors="replace")


def _raise_invalid_api_key_response(message: str, status_code: int, body: bytes) -> NoReturn:
    """不正な API キー発行 API レスポンスを例外として送出する。

    Args:
        message: レスポンスが不正な理由
        status_code: HTTP ステータスコード
        body: レスポンス本文

    Raises:
        ApiKeyApiError: レスポンスが API の期待形式でない場合
    """
    raise ApiKeyApiError(
        f"API key API returned an invalid response: {message}",
        status_code=status_code,
        body=_response_body_text(body),
        raw_body=body,
    )


def _serialize_expires_in(expires_in: int | str | timedelta | None) -> str | None:
    """有効期限指定を API の文字列表現へ変換する。

    Args:
        expires_in: ミリ秒の整数、API の単位付き文字列、または期間

    Returns:
        API の ``epi`` パラメータへ渡す文字列。未指定の場合は ``None``

    Raises:
        ConfigurationError: 有効期限の型が対応していない場合
    """
    if expires_in is None:
        return None
    if isinstance(expires_in, bool):
        raise ConfigurationError("expires_in must be an integer, string, or timedelta")
    if isinstance(expires_in, int | str):
        return str(expires_in)
    if isinstance(expires_in, timedelta):
        return str(int(expires_in.total_seconds() * 1000))
    raise ConfigurationError("expires_in must be an integer, string, or timedelta")


def _resolve_api_key_authentication(api_key: str | None) -> str:
    """引数と環境変数からAPIキー発行APIの認証情報を解決する。

    Args:
        api_key: API キー発行機能付き API キー

    Returns:
        Bearer認証に使用する解決済みAPIキー

    Raises:
        AuthenticationError: API キーが指定されていない場合
    """
    resolved_api_key = api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY")
    if resolved_api_key is None:
        raise AuthenticationError("AMIVOICE_API_KEY is not set")
    return resolved_api_key


class ApiKeyClient:
    """AmiVoice API キー発行 API のクライアント。

    API キー発行機能付き API キーによる Bearer 認証を使用して API キーを発行する。

    Args:
        api_key: API キー発行機能付き API キー。省略時は ``AMIVOICE_API_KEY`` を使用する
        base_url: API のベース URL
        timeout: HTTP 接続のタイムアウト秒数
        transport: テスト用トランスポート

    Raises:
        AuthenticationError: API キーが指定されていない場合
        ConfigurationError: ベース URL が不正な場合
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        transport: ApiKeyTransport | None = None,
    ) -> None:
        """クライアント設定とトランスポートを初期化する。

        Args:
            api_key: API キー発行機能付き API キー。省略時は ``AMIVOICE_API_KEY`` を使用する
            base_url: API のベース URL
            timeout: HTTP 接続のタイムアウト秒数
            transport: テスト用トランスポート

        Raises:
            AuthenticationError: API キーが指定されていない場合
            ConfigurationError: ベース URL が不正な場合
        """
        resolved_api_key = _resolve_api_key_authentication(api_key)
        parsed_base_url = urlsplit(base_url)
        if parsed_base_url.scheme != "https" or not parsed_base_url.netloc:
            raise ConfigurationError("base_url must be an absolute HTTPS URL")
        if parsed_base_url.query or parsed_base_url.fragment:
            raise ConfigurationError("base_url must not contain a query or fragment")

        self._api_key = resolved_api_key
        self._endpoint_url = f"{base_url.rstrip('/')}{_ISSUE_API_PATH}"
        self._transport = transport if transport is not None else _HttpApiKeyTransport(timeout)

    def issue(
        self,
        *,
        expires_in: int | str | timedelta | None = None,
        allowed_ip_addresses: Sequence[str] | None = None,
    ) -> str:
        """有効期限と接続元IP制限を指定してAPIキーを発行する。

        Args:
            expires_in: 有効期限。整数はミリ秒、文字列は ``2h`` などの API 形式、期間はミリ秒へ変換する
            allowed_ip_addresses: API キーを利用できる接続元 IP アドレスまたは CIDR の一覧

        Returns:
            発行された API キー文字列

        Raises:
            ApiKeyApiError: API がエラーを返した場合、またはレスポンスが空の場合
            ConnectionFailedError: 通信に失敗した場合
            ConfigurationError: 有効期限の型が対応していない場合
        """
        form: dict[str, str] = {}
        serialized_expires_in = _serialize_expires_in(expires_in)
        if serialized_expires_in is not None:
            form["epi"] = serialized_expires_in
        if allowed_ip_addresses is not None:
            form["ipa"] = ",".join(allowed_ip_addresses)

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self._api_key}",
        }
        body = urlencode(form).encode("utf-8")

        try:
            status_code, response_body = self._transport.request("POST", self._endpoint_url, headers, body)
        except (OSError, http.client.HTTPException) as exc:
            raise ConnectionFailedError(f"API key API connection failed: {exc}") from exc
        if not 200 <= status_code < 300:
            body_text = _response_body_text(response_body)
            raise ApiKeyApiError(
                f"API key API request failed with HTTP {status_code}: {body_text}",
                status_code=status_code,
                body=body_text,
                raw_body=response_body,
            )

        api_key_text = _response_body_text(response_body).strip()
        if not api_key_text:
            _raise_invalid_api_key_response("response body must contain an API key", status_code, response_body)
        return api_key_text
