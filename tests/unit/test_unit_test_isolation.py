"""実APIの認証情報と外部ネットワークから単体テストを隔離する"""

import os
import socket

import pytest

from tests.unit.conftest import require_loopback_host


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "127.0.0.2", "::1"])
def test_require_loopback_host_localhost_valid_return(host: str) -> None:
    """loopbackだけを許可する"""
    # Given: localhostまたはloopbackのIPアドレス
    # When / Then: DNS解決や通信を起こさず許可する
    require_loopback_host(host)


@pytest.mark.parametrize("host", ["acp-api.amivoice.com", "acp-dsrpp.amivoice.com", "192.0.2.1", "::", "0.0.0.0"])
def test_require_loopback_host_external_invalid_raise_AssertionError(host: str) -> None:
    """外部接続先をDNS解決より前に拒否する"""
    # Given: サービスのホスト名または非loopbackアドレス
    # When / Then: 送受信を行わず拒否する
    with pytest.raises(AssertionError, match="non-loopback"):
        require_loopback_host(host)


def test_unit_environment_actual_credentials_invalid_omit_keys() -> None:
    """実キーのある環境からpytestを起動してもキーを引き継がない"""
    # Given: 単体テスト共通の自動fixture
    # When: 認証環境変数の有無だけを確認する、値は取得・表示しない
    credentials_absent = all(name not in os.environ for name in ("AMIVOICE_API_KEY", "AMIVOICE_ISSUER_API_KEY"))
    # Then: 実キーはテストケースから参照できない
    assert credentials_absent


def test_unit_network_external_dns_invalid_raise_AssertionError() -> None:
    """外部DNSをネットワーク呼び出しの前に拒否する"""
    # Given: 単体テスト共通のネットワークガード
    # When / Then: APIの名前解決を試みても送信しない
    with pytest.raises(AssertionError, match="non-loopback"):
        socket.getaddrinfo("acp-api.amivoice.com", 443)


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_unit_network_external_socket_invalid_raise_AssertionError(method: str) -> None:
    """DNSを使わない直接のIP接続も送信前に拒否する"""
    # Given: テスト用ソケットと予約済みTEST-NETアドレス
    # When / Then: どちらの接続APIでも送信前に拒否する
    with socket.socket() as connection, pytest.raises(AssertionError, match="non-loopback"):
        getattr(connection, method)(("192.0.2.1", 443))
