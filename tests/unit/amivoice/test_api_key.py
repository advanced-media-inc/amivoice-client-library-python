"""API キー発行 API クライアントのユニットテスト。"""

from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qs

import pytest

from amivoice import ApiKeyApiError, ApiKeyClient, AuthenticationError, ConfigurationError, ConnectionFailedError


@dataclass
class FakeApiKeyTransport:
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


@pytest.mark.parametrize("base_url", ["https://example.test/api?tenant=1", "https://example.test/api#fragment"])
def test_api_key_client_base_url_with_query_or_fragment_invalid_raise_ConfigurationError(
    base_url: str,
) -> None:
    """クエリまたはフラグメントを含むベースURLでConfigurationErrorが送出されることを確認する。"""
    # Given: クエリまたはフラグメントを含むベースURL
    # When / Then: クライアント生成が拒否される
    with pytest.raises(ConfigurationError, match="query or fragment"):
        ApiKeyClient(api_key="issuer-key", base_url=base_url)


def test_api_key_client_issue_bearer_valid_sends_authorization_and_returns_key() -> None:
    """Bearer認証でAPIキーを発行し、レスポンス本文を返すことを確認する。"""
    # Given: Bearer認証とAPIキーを返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(200, b"issued-key\n")])
    client = ApiKeyClient(api_key="issuer-key", base_url="https://example.test", transport=transport)

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
    [(1234, "1234"), ("2h", "2h"), (timedelta(milliseconds=1500), "1500")],
)
def test_api_key_client_issue_expires_in_valid_serializes_value(expires_in: int | str | timedelta, expected: str) -> None:
    """有効期限の各型がepiフォーム値へ変換されることを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(200, b"issued-key")])
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When: 有効期限の型を変えてAPIキーを発行する
    client.issue(expires_in=expires_in)

    # Then: epiが指定値へ変換される
    assert parse_qs(transport.requests[0][3].decode("utf-8")) == {"epi": [expected]}


def test_api_key_client_issue_allowed_ip_addresses_string_invalid_raise_ConfigurationError() -> None:
    """IPアドレス制限に単一文字列を指定するとConfigurationErrorが送出されることを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(200, b"issued-key")])
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When / Then: 単一文字列のIPアドレス制限が拒否される
    with pytest.raises(ConfigurationError, match="allowed_ip_addresses"):
        client.issue(allowed_ip_addresses="203.0.113.1")

    assert transport.requests == []


def test_api_key_client_issue_without_optional_parameters_valid_omits_form_values() -> None:
    """任意パラメータを省略した場合にフォームへ追加しないことを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(200, b"issued-key")])
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When: 任意パラメータを省略してAPIキーを発行する
    client.issue()

    # Then: 空のフォーム本文が送信される
    assert transport.requests[0][3] == b""


def test_api_key_client_environment_credentials_valid_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """認証情報を省略した場合にAMIVOICE_API_KEYを使用することを確認する。"""
    # Given: APIキーの環境変数
    monkeypatch.setenv("AMIVOICE_API_KEY", "env-issuer-key")
    transport = FakeApiKeyTransport(responses=[(200, b"issued-key")])

    # When: 認証情報を省略してクライアントを生成し、発行する
    client = ApiKeyClient(transport=transport)
    client.issue()

    # Then: 環境変数のAPIキーがBearer認証で送信される
    assert transport.requests[0][2]["Authorization"] == "Bearer env-issuer-key"


def test_api_key_client_missing_credentials_invalid_raise_AuthenticationError(monkeypatch: pytest.MonkeyPatch) -> None:
    """認証情報がない場合にAuthenticationErrorが送出されることを確認する。"""
    # Given: APIキーの環境変数を削除する
    monkeypatch.delenv("AMIVOICE_API_KEY", raising=False)

    # When / Then: 認証情報なしのクライアント生成でAuthenticationErrorが送出される
    with pytest.raises(AuthenticationError):
        ApiKeyClient()


def test_api_key_client_api_error_invalid_raise_ApiKeyApiError_with_status_and_body() -> None:
    """非2xxレスポンスでApiKeyApiErrorが送出され詳細を保持することを確認する。"""
    # Given: HTTPエラーを返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(403, b"forbidden")])
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でApiKeyApiErrorが送出される
    with pytest.raises(ApiKeyApiError, match="HTTP 403") as exc_info:
        client.issue()

    assert exc_info.value.status_code == 403
    assert exc_info.value.body == "forbidden"


def test_api_key_client_invalid_utf8_success_response_invalid_raise_ApiKeyApiError_with_raw_body() -> None:
    """不正なUTF-8の成功本文でApiKeyApiErrorが送出され生本文を保持することを確認する。"""
    # Given: 不正なUTF-8本文を返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(200, b"\xff")])
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でApiKeyApiErrorが送出される
    with pytest.raises(ApiKeyApiError, match="invalid UTF-8") as exc_info:
        client.issue()

    assert exc_info.value.status_code == 200
    assert exc_info.value.raw_body == b"\xff"


def test_api_key_client_empty_response_invalid_raise_ApiKeyApiError() -> None:
    """空の成功レスポンスでApiKeyApiErrorが送出されることを確認する。"""
    # Given: 空本文の成功レスポンスを返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(200, b"")])
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でApiKeyApiErrorが送出される
    with pytest.raises(ApiKeyApiError, match="response body"):
        client.issue()


def test_api_key_client_network_failure_invalid_raise_ConnectionFailedError() -> None:
    """通信エラーでConnectionFailedErrorが送出されることを確認する。"""
    # Given: 接続エラーを送出するフェイクトランスポート
    transport = FakeApiKeyTransport(error=OSError("connection refused"))
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When / Then: APIキー発行でConnectionFailedErrorが送出される
    with pytest.raises(ConnectionFailedError, match="connection refused") as exc_info:
        client.issue()

    assert isinstance(exc_info.value.__cause__, OSError)


def test_api_key_client_expires_in_invalid_raise_ConfigurationError() -> None:
    """未対応の有効期限型でConfigurationErrorが送出されることを確認する。"""
    # Given: APIキーを返すフェイクトランスポート
    transport = FakeApiKeyTransport(responses=[(200, b"issued-key")])
    client = ApiKeyClient(api_key="issuer-key", transport=transport)

    # When / Then: boolの有効期限が拒否される
    with pytest.raises(ConfigurationError, match="expires_in"):
        client.issue(expires_in=True)  # type: ignore[arg-type]
