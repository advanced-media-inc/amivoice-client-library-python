"""AmiVoice API キー発行 API の高レベルクライアント。"""

import http.client
import ipaddress
import os
from collections.abc import Sequence
from datetime import timedelta
from typing import NoReturn, Protocol
from urllib.parse import urlencode, urlsplit

from ._connection_settings import parse_service_url
from ._http_api import HttpApiConnection, validate_service_api_key
from .exceptions import ApiKeyIssuanceApiError, AuthenticationError, ConfigurationError, ConnectionFailedError

__all__ = ["ApiKeyIssuanceClient", "ApiKeyIssuanceTransport"]

_DEFAULT_BASE_URL = "https://acp-api.amivoice.com"
_ISSUE_API_PATH = "/issue_service_authorization"
_ISSUER_API_KEY_ENVIRONMENT_VARIABLE = "AMIVOICE_ISSUER_API_KEY"

# API キーを利用できる接続元 IPv4 アドレスまたは IPv4 CIDR の指定
_AllowedIpAddress = str | ipaddress.IPv4Address | ipaddress.IPv4Network


class ApiKeyIssuanceTransport(Protocol):
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


def _response_body_text(body: bytes) -> str:
    """レスポンス本文を表示用の文字列へ変換する。"""
    return body.decode("utf-8", errors="replace")


def _decode_api_key_issuance_response_body(body: bytes, status_code: int) -> str:
    """API キー発行 API の成功本文を厳密な UTF-8 としてデコードする。

    Args:
        body: API キー発行 API のレスポンス本文
        status_code: HTTP ステータスコード

    Returns:
        UTF-8 としてデコードしたレスポンス本文

    Raises:
        ApiKeyIssuanceApiError: レスポンス本文が UTF-8 として不正な場合
    """
    try:
        return body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ApiKeyIssuanceApiError(
            f"API key issuance API returned invalid UTF-8 response: {exc}",
            status_code=status_code,
            body=_response_body_text(body),
            raw_body=body,
        ) from exc


def _raise_invalid_api_key_issuance_response(message: str, status_code: int, body: bytes) -> NoReturn:
    """不正な API キー発行 API レスポンスを例外として送出する。

    Args:
        message: レスポンスが不正な理由
        status_code: HTTP ステータスコード
        body: レスポンス本文

    Raises:
        ApiKeyIssuanceApiError: レスポンスが API の期待形式でない場合
    """
    raise ApiKeyIssuanceApiError(
        f"API key issuance API returned an invalid response: {message}",
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
        ConfigurationError: 有効期限の型が対応していない場合、または整数か期間が 1 ミリ秒未満の場合
    """
    if expires_in is None:
        return None
    if isinstance(expires_in, bool):
        raise ConfigurationError("expires_in must be an integer, string, or timedelta")
    if isinstance(expires_in, str):
        return expires_in
    if isinstance(expires_in, int):
        expires_in_milliseconds = expires_in
    elif isinstance(expires_in, timedelta):
        # total_seconds() の浮動小数では 1001 ミリ秒が 1000 になるため、整数のまま計算する
        expires_in_milliseconds = expires_in // timedelta(milliseconds=1)
    else:
        raise ConfigurationError("expires_in must be an integer, string, or timedelta")
    if expires_in_milliseconds <= 0:
        raise ConfigurationError("expires_in must be at least 1 millisecond")
    return str(expires_in_milliseconds)


def _serialize_allowed_ip_address(allowed_ip_address: _AllowedIpAddress) -> str:
    """接続元 IP 制限の 1 要素を検証して API の文字列表現へ変換する。

    Args:
        allowed_ip_address: IPv4 アドレス、IPv4 CIDR の文字列、または ipaddress の IPv4 オブジェクト

    Returns:
        API の ``ipa`` パラメータへ渡す 1 要素分の文字列

    Raises:
        ConfigurationError: IPv4 アドレスまたは IPv4 CIDR として解釈できない場合
    """
    if isinstance(allowed_ip_address, ipaddress.IPv4Address | ipaddress.IPv4Network):
        return str(allowed_ip_address)
    if not isinstance(allowed_ip_address, str):
        raise ConfigurationError("allowed_ip_addresses must contain IPv4 address or IPv4 CIDR values")
    try:
        # API は IPv4 CIDR だけを受け付けるため、IPv6 や区切り文字を含む値は送信前に拒否する
        ipaddress.IPv4Network(allowed_ip_address, strict=False)
    except ValueError as exc:
        message = f"allowed_ip_addresses contains an invalid IPv4 address or CIDR: {allowed_ip_address!r}"
        raise ConfigurationError(message) from exc
    return allowed_ip_address


def _serialize_allowed_ip_addresses(allowed_ip_addresses: Sequence[_AllowedIpAddress] | None) -> str | None:
    """接続元 IP 制限を検証して API の文字列表現へ変換する。

    Args:
        allowed_ip_addresses: API キーを利用できる接続元 IPv4 アドレスまたは CIDR の一覧

    Returns:
        API の ``ipa`` パラメータへ渡すカンマ区切り文字列。未指定の場合は ``None``

    Raises:
        ConfigurationError: 単一文字列、空の一覧、または IPv4 として不正な値を指定した場合
    """
    if allowed_ip_addresses is None:
        return None
    if isinstance(allowed_ip_addresses, str):
        raise ConfigurationError("allowed_ip_addresses must be a sequence of strings, not a string")
    if len(allowed_ip_addresses) == 0:
        # 空の一覧は ipa= となり、制限したつもりで制限なしのキーが発行されるため拒否する
        raise ConfigurationError("allowed_ip_addresses must not be empty; omit it to issue an API key without IP restriction")
    return ",".join(_serialize_allowed_ip_address(allowed_ip_address) for allowed_ip_address in allowed_ip_addresses)


def _contains_control_character(value: str) -> bool:
    """文字列が HTTP ヘッダー値に使えない制御文字を含むかを判定する。

    Args:
        value: 判定する文字列

    Returns:
        CR、LF などの ASCII 制御文字を含む場合は ``True``
    """
    return any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)


def _resolve_api_key_issuance_authentication(api_key: str | None) -> str:
    """引数と環境変数からAPIキー発行APIの認証情報を解決する。

    Args:
        api_key: API キー発行機能付き API キー

    Returns:
        Bearer認証に使用する解決済みAPIキー

    Raises:
        AuthenticationError: API キーが指定されていない場合
        ConfigurationError: API キーが制御文字を含む場合
    """
    # 音声認識用の AMIVOICE_API_KEY を発行用として誤送信しないよう、発行専用の環境変数から読む
    resolved_api_key = api_key if api_key is not None else os.environ.get(_ISSUER_API_KEY_ENVIRONMENT_VARIABLE)
    if resolved_api_key is None:
        raise AuthenticationError(f"{_ISSUER_API_KEY_ENVIRONMENT_VARIABLE} is not set")
    if _contains_control_character(resolved_api_key):
        # 値を例外メッセージへ含めると発行権限付きキーがログへ漏れるため、理由だけを伝える
        raise ConfigurationError("api_key must not contain control characters such as CR or LF")
    return resolved_api_key


class ApiKeyIssuanceClient:
    """AmiVoice API キー発行 API のクライアント。

    API キー発行機能付き API キーによる Bearer 認証を使用して API キーを発行する。

    Args:
        api_key: API キー発行機能付き API キー。省略時は ``AMIVOICE_ISSUER_API_KEY`` を使用する
        base_url: API のベース URL
        timeout: HTTP 接続のタイムアウト秒数
        transport: テスト用トランスポート

    Raises:
        AuthenticationError: API キーが指定されていない場合
        ConfigurationError: API キーが制御文字を含む場合、またはベース URL が不正な場合
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        transport: ApiKeyIssuanceTransport | None = None,
    ) -> None:
        """クライアント設定とトランスポートを初期化する。

        Args:
            api_key: API キー発行機能付き API キー。省略時は ``AMIVOICE_ISSUER_API_KEY`` を使用する
            base_url: API のベース URL
            timeout: HTTP 接続のタイムアウト秒数
            transport: テスト用トランスポート

        Raises:
            AuthenticationError: API キーが指定されていない場合
            ConfigurationError: API キーが制御文字を含む場合、またはベース URL が不正な場合
        """
        resolved_api_key = _resolve_api_key_issuance_authentication(api_key)
        parsed_base_url = urlsplit(base_url)
        if parsed_base_url.scheme != "https" or not parsed_base_url.netloc:
            raise ConfigurationError("base_url must be an absolute HTTPS URL")
        if parsed_base_url.query or parsed_base_url.fragment:
            raise ConfigurationError("base_url must not contain a query or fragment")

        parse_service_url(base_url, ("https",))
        self._api_key = validate_service_api_key(resolved_api_key)
        self._endpoint_url = f"{base_url.rstrip('/')}{_ISSUE_API_PATH}"
        self._transport = transport if transport is not None else HttpApiConnection(timeout)

    def issue(
        self,
        *,
        expires_in: int | str | timedelta | None = None,
        allowed_ip_addresses: Sequence[_AllowedIpAddress] | None = None,
    ) -> str:
        """有効期限と接続元IP制限を指定してAPIキーを発行する。

        Args:
            expires_in: 有効期限。省略時は 30 秒。整数はミリ秒、文字列は ``2h`` などの API 形式、期間はミリ秒へ変換する
            allowed_ip_addresses: API キーを利用できる接続元 IPv4 アドレスまたは IPv4 CIDR の一覧。省略時は制限しない

        Returns:
            発行された API キー文字列

        Raises:
            ApiKeyIssuanceApiError: API がエラーを返した場合、またはレスポンスが空の場合
            ConnectionFailedError: 通信に失敗した場合
            ConfigurationError: 有効期限の型が対応していない場合、有効期限が 1 ミリ秒未満の場合、または接続元 IP 制限が不正な場合
        """
        form: dict[str, str] = {}
        serialized_expires_in = _serialize_expires_in(expires_in)
        if serialized_expires_in is not None:
            form["epi"] = serialized_expires_in
        serialized_allowed_ip_addresses = _serialize_allowed_ip_addresses(allowed_ip_addresses)
        if serialized_allowed_ip_addresses is not None:
            form["ipa"] = serialized_allowed_ip_addresses

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self._api_key}",
        }
        body = urlencode(form).encode("utf-8")

        try:
            status_code, response_body = self._transport.request("POST", self._endpoint_url, headers, body)
        except (OSError, http.client.HTTPException) as exc:
            raise ConnectionFailedError("API key issuance API connection failed") from None
        if not 200 <= status_code < 300:
            body_text = _response_body_text(response_body)
            raise ApiKeyIssuanceApiError(
                f"API key issuance API request failed with HTTP {status_code}: {body_text}",
                status_code=status_code,
                body=body_text,
                raw_body=response_body,
            )

        api_key_text = _decode_api_key_issuance_response_body(response_body, status_code).strip()
        if not api_key_text:
            _raise_invalid_api_key_issuance_response("response body must contain an API key", status_code, response_body)
        return api_key_text
