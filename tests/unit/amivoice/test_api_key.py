"""API キー発行 API クライアントのユニットテスト。"""

import ipaddress
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qs

import pytest

from amivoice import ApiKeyIssuanceApiError, ApiKeyIssuanceClient, AuthenticationError, ConfigurationError, ConnectionFailedError


@dataclass
class FakeApiKeyIssuanceTransport:
    """テスト用の API キー発行 API トランスポート。"""

    responses: list[tuple[int, bytes]] = field(default_factory=list)
    error: Exception | None = None
    requests: list[tuple[str, str, dict[str, str], bytes | None]] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        """リクエストを記録し、キューからレスポンスを返す。"""
        self.requests.append((method, url, headers, body))
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def clear_api_key_authentication_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """APIキー発行の認証環境変数を各テスト前に削除する。"""
    for variable_name in ("AMIVOICE_API_KEY", "AMIVOICE_ISSUER_API_KEY"):
        monkeypatch.delenv(variable_name, raising=False)


@pytest.mark.parametrize("base_url", ["https://example.test/api?tenant=1", "https://example.test/api#fragment"])
def test_api_key_issuance_client_base_url_with_query_or_fragment_invalid_raise_ConfigurationError(
    base_url: str,
) -> None:
    """クエリまたはフラグメントを含むベースURLでConfigurationErrorが送出されることを確認する。"""
    # Given: クエリまたはフラグメントを含むベースURL
    # When / Then: クライアント生成が拒否される
    with pytest.raises(ConfigurationError, match="query or fragment"):
        ApiKeyIssuanceClient(api_key="issuer-key", base_url=base_url)


@pytest.mark.parametrize("api_key", ["secret-issuer-key\n", "secret-issuer-key\r\n", "secret\x00issuer-key"])
def test_api_key_issuance_client_api_key_control_character_invalid_raise_ConfigurationError_without_key(api_key: str) -> None:
    """制御文字を含むAPIキーを値を表示せずにConfigurationErrorで拒否することを確認する。"""
    # Given: 送信されると記録されるフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])

    # When / Then: クライアント生成が拒否され、例外メッセージにキーが含まれない
    with pytest.raises(ConfigurationError, match="control characters") as exc_info:
        ApiKeyIssuanceClient(api_key=api_key, transport=transport)

    assert "secret" not in str(exc_info.value)
    assert transport.requests == []


def test_api_key_issuance_client_environment_api_key_control_character_invalid_raise_ConfigurationError(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """環境変数のAPIキーが改行を含む場合もConfigurationErrorで拒否することを確認する。"""
    # Given: 末尾に改行を含むAPIキーの環境変数
    monkeypatch.setenv("AMIVOICE_ISSUER_API_KEY", "secret-issuer-key\n")

    # When / Then: クライアント生成が拒否され、例外メッセージにキーが含まれない
    with pytest.raises(ConfigurationError, match="control characters") as exc_info:
        ApiKeyIssuanceClient()

    assert "secret" not in str(exc_info.value)


def test_api_key_issuance_client_issue_bearer_valid_sends_authorization_and_returns_key() -> None:
    """Bearer認証でAPIキーを発行し、レスポンス本文を返すことを確認する。"""
    # Given: Bearer認証とAPIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key\n")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", base_url="https://example.test", transport=transport)

    # When: 有効期限とIP制限を指定してAPIキーを発行する
    issued_key = client.issue(expires_in=7_200_000, allowed_ip_addresses=("203.0.113.1", "198.51.100.0/24"))

    # Then: Bearer認証、フォーム、戻り値が正しい
    assert issued_key == "issued-key"
    assert transport.requests == [
        (
            "POST",
            "https://example.test/issue_service_authorization",
            {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": "Bearer issuer-key",
            },
            b"epi=7200000&ipa=203.0.113.1%2C198.51.100.0%2F24",
        )
    ]


@pytest.mark.parametrize(
    ("expires_in", "expected"),
    [
        (1234, "1234"),
        (1, "1"),
        ("2h", "2h"),
        (timedelta(milliseconds=1500), "1500"),
        (timedelta(milliseconds=1001), "1001"),
        (timedelta(milliseconds=1, microseconds=999), "1"),
        (timedelta(days=100), "8640000000"),
    ],
)
def test_api_key_issuance_client_issue_expires_in_valid_serializes_value(
    expires_in: int | str | timedelta,
    expected: str,
) -> None:
    """有効期限の各型がepiフォーム値へ変換されることを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When: 有効期限の型を変えてAPIキーを発行する
    client.issue(expires_in=expires_in)

    # Then: epiが指定値へ変換される
    assert parse_qs(transport.requests[0][3].decode("utf-8")) == {"epi": [expected]}


@pytest.mark.parametrize(
    "expires_in",
    [0, -5, timedelta(0), timedelta(microseconds=999), timedelta(milliseconds=-1)],
)
def test_api_key_issuance_client_issue_expires_in_not_positive_invalid_raise_ConfigurationError(
    expires_in: int | timedelta,
) -> None:
    """1ミリ秒未満の整数または期間でConfigurationErrorが送出され送信しないことを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: 0以下の有効期限が拒否される
    with pytest.raises(ConfigurationError, match="at least 1 millisecond"):
        client.issue(expires_in=expires_in)

    assert transport.requests == []


def test_api_key_issuance_client_issue_allowed_ip_addresses_string_invalid_raise_ConfigurationError() -> None:
    """IPアドレス制限に単一文字列を指定するとConfigurationErrorが送出されることを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: 単一文字列のIPアドレス制限が拒否される
    with pytest.raises(ConfigurationError, match="allowed_ip_addresses"):
        client.issue(allowed_ip_addresses="203.0.113.1")

    assert transport.requests == []


def test_api_key_issuance_client_issue_allowed_ip_addresses_ipaddress_objects_valid_serializes_value() -> None:
    """ipaddressのIPv4オブジェクトをIP制限として送信できることを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When: IPv4アドレスとIPv4ネットワークのオブジェクトを指定してAPIキーを発行する
    client.issue(
        allowed_ip_addresses=(ipaddress.IPv4Address("203.0.113.1"), ipaddress.IPv4Network("198.51.100.0/24")),
    )

    # Then: ipaが文字列表現のカンマ区切りになる
    assert parse_qs(transport.requests[0][3].decode("utf-8")) == {"ipa": ["203.0.113.1,198.51.100.0/24"]}


def test_api_key_issuance_client_issue_allowed_ip_addresses_empty_invalid_raise_ConfigurationError() -> None:
    """空のIP制限一覧でConfigurationErrorが送出され送信しないことを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: 空の一覧が拒否される
    with pytest.raises(ConfigurationError, match="must not be empty"):
        client.issue(allowed_ip_addresses=[])

    assert transport.requests == []


@pytest.mark.parametrize(
    "allowed_ip_address",
    ["::1", "2001:db8::/32", "not-an-ip", "203.0.113.1 198.51.100.1", "", "203.0.113.0/33", 1, ipaddress.IPv6Address("::1")],
)
def test_api_key_issuance_client_issue_allowed_ip_addresses_non_ipv4_invalid_raise_ConfigurationError(
    allowed_ip_address: object,
) -> None:
    """IPv4アドレスまたはIPv4 CIDRでない値でConfigurationErrorが送出され送信しないことを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: 不正な値を含むIP制限が拒否される
    with pytest.raises(ConfigurationError, match="allowed_ip_addresses"):
        client.issue(allowed_ip_addresses=["203.0.113.1", allowed_ip_address])  # type: ignore[list-item]

    assert transport.requests == []


def test_api_key_issuance_client_issue_without_optional_parameters_valid_omits_form_values() -> None:
    """任意パラメータを省略した場合にフォームへ追加しないことを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When: 任意パラメータを省略してAPIキーを発行する
    client.issue()

    # Then: 空のフォーム本文が送信される
    assert transport.requests[0][3] == b""


def test_api_key_issuance_client_environment_credentials_valid_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """認証情報を省略した場合にAMIVOICE_ISSUER_API_KEYを使用することを確認する。"""
    # Given: APIキーの環境変数
    monkeypatch.setenv("AMIVOICE_ISSUER_API_KEY", "env-issuer-key")
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])

    # When: 認証情報を省略してクライアントを生成し、発行する
    client = ApiKeyIssuanceClient(transport=transport)
    client.issue()

    # Then: 環境変数のAPIキーがBearer認証で送信される
    assert transport.requests[0][2]["Authorization"] == "Bearer env-issuer-key"


def test_api_key_issuance_client_recognition_api_key_environment_ignored_raise_AuthenticationError(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """音声認識用のAMIVOICE_API_KEYを発行用のAPIキーとして使用しないことを確認する。"""
    # Given: 音声認識用のAPIキーだけを設定した環境変数
    monkeypatch.setenv("AMIVOICE_API_KEY", "recognition-key")
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])

    # When / Then: 発行用のAPIキーがないためクライアント生成が拒否される
    with pytest.raises(AuthenticationError, match="AMIVOICE_ISSUER_API_KEY"):
        ApiKeyIssuanceClient(transport=transport)

    assert transport.requests == []


def test_api_key_issuance_client_missing_credentials_invalid_raise_AuthenticationError(monkeypatch: pytest.MonkeyPatch) -> None:
    """認証情報がない場合にAuthenticationErrorが送出されることを確認する。"""
    # Given: APIキーの環境変数を削除する
    monkeypatch.delenv("AMIVOICE_ISSUER_API_KEY", raising=False)

    # When / Then: 認証情報なしのクライアント生成でAuthenticationErrorが送出される
    with pytest.raises(AuthenticationError):
        ApiKeyIssuanceClient()


def test_api_key_issuance_client_api_error_invalid_raise_ApiKeyIssuanceApiError_with_status_and_body() -> None:
    """非2xxレスポンスでApiKeyIssuanceApiErrorが送出され詳細を保持することを確認する。"""
    # Given: HTTPエラーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(403, b"forbidden")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でApiKeyIssuanceApiErrorが送出される
    with pytest.raises(ApiKeyIssuanceApiError, match="HTTP 403") as exc_info:
        client.issue()

    assert exc_info.value.status_code == 403
    assert exc_info.value.body == "forbidden"


def test_api_key_issuance_client_invalid_utf8_success_response_invalid_raise_ApiKeyIssuanceApiError_with_raw_body() -> None:
    """不正なUTF-8の成功本文でApiKeyIssuanceApiErrorが送出され生本文を保持することを確認する。"""
    # Given: 不正なUTF-8本文を返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"\xff")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でApiKeyIssuanceApiErrorが送出される
    with pytest.raises(ApiKeyIssuanceApiError, match="invalid UTF-8") as exc_info:
        client.issue()

    assert exc_info.value.status_code == 200
    assert exc_info.value.raw_body == b"\xff"


def test_api_key_issuance_client_empty_response_invalid_raise_ApiKeyIssuanceApiError() -> None:
    """空の成功レスポンスでApiKeyIssuanceApiErrorが送出されることを確認する。"""
    # Given: 空本文の成功レスポンスを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でApiKeyIssuanceApiErrorが送出される
    with pytest.raises(ApiKeyIssuanceApiError, match="response body"):
        client.issue()


def test_api_key_issuance_client_network_failure_invalid_raise_ConnectionFailedError() -> None:
    """通信エラーでConnectionFailedErrorが送出されることを確認する。"""
    # Given: 接続エラーを送出するフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(error=OSError("connection refused"))
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でConnectionFailedErrorが送出される
    with pytest.raises(ConnectionFailedError, match="connection refused") as exc_info:
        client.issue()

    assert isinstance(exc_info.value.__cause__, OSError)


def test_api_key_issuance_client_expires_in_invalid_raise_ConfigurationError() -> None:
    """未対応の有効期限型でConfigurationErrorが送出されることを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyIssuanceTransport(responses=[(200, b"issued-key")])
    client = ApiKeyIssuanceClient(api_key="issuer-key", transport=transport)

    # When / Then: boolの有効期限が拒否される
    with pytest.raises(ConfigurationError, match="expires_in"):
        client.issue(expires_in=True)  # type: ignore[arg-type]
