"""単体テストのパスと外部通信・認証情報の隔離を設定する"""

import ipaddress
import socket
import sys
from pathlib import Path

import pytest

_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ORIGINAL_GETADDRINFO = socket.getaddrinfo


def require_loopback_host(host: str | bytes) -> None:
    """非loopbackへの接続をDNS解決より前に拒否する

    Args:
        host (str | bytes): 名前解決または接続の対象

    Raises:
        AssertionError: 外部への通信を試みた場合
    """
    if host in ("localhost", b"localhost"):
        return
    try:
        address = ipaddress.ip_address(host.decode("ascii") if isinstance(host, bytes) else host)
    except (ValueError, UnicodeError):
        raise AssertionError("Unit tests must not access non-loopback networks") from None
    if not address.is_loopback:
        raise AssertionError("Unit tests must not access non-loopback networks")


def _loopback_connect(connection: socket.socket, address: tuple | str | bytes) -> None:
    """直接のソケット接続もloopbackだけに制限する"""
    if isinstance(address, tuple):
        require_loopback_host(address[0])
    return _ORIGINAL_CONNECT(connection, address)


def _loopback_connect_ex(connection: socket.socket, address: tuple | str | bytes) -> int:
    """例外なし接続APIにも同じ制限を適用する"""
    if isinstance(address, tuple):
        require_loopback_host(address[0])
    return _ORIGINAL_CONNECT_EX(connection, address)


def _loopback_getaddrinfo(host: str | bytes, port: str | int, *args: object, **kwargs: object) -> list:
    """外部DNSへの問い合わせを事前に拒否する"""
    require_loopback_host(host)
    return _ORIGINAL_GETADDRINFO(host, port, *args, **kwargs)


@pytest.fixture(autouse=True)
def isolate_unit_test_credentials_and_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """実キーを継承せず、localhost以外への単体テスト通信を禁止する"""
    monkeypatch.delenv("AMIVOICE_API_KEY", raising=False)
    monkeypatch.delenv("AMIVOICE_ISSUER_API_KEY", raising=False)
    monkeypatch.setattr(socket.socket, "connect", _loopback_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _loopback_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", _loopback_getaddrinfo)


repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "src"))
