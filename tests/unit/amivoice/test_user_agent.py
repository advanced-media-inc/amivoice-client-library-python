"""ライブラリ識別子をHTTP・WebSocket・CONNECTで共通に送信する"""

import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest

from amivoice._http_api import HttpApiConnection
from amivoice._http_recognition import HttpRecognitionConnection
from amivoice._params import RecognitionParams
from amivoice._user_agent import build_client_user_agent
from amivoice._websocket_connection import WebSocketConnection

_EXPECTED_USER_AGENT = f"amivoice-api-client/1.2.3 Python/{sys.version_info.major}.{sys.version_info.minor}"


def test_build_client_user_agent_installed_metadata_valid_return_version() -> None:
    """配布パッケージのバージョンとPythonのメジャー・マイナーを使う"""
    # Given: インストールされた配布パッケージのメタデータ
    with patch("amivoice._user_agent.version", return_value="1.2.3") as metadata_version:
        # When: HTTPのUser-Agentを生成する
        user_agent = build_client_user_agent()
    # Then: 正しい配布名でバージョンを問い合わせる
    assert user_agent == _EXPECTED_USER_AGENT
    metadata_version.assert_called_once_with("amivoice-api-client")


def test_build_client_user_agent_missing_metadata_valid_return_fallback() -> None:
    """ソース直接実行時もバージョン情報の欠落で通信を止めない"""
    # Given: 配布メタデータがない環境
    with patch("amivoice._user_agent.version", side_effect=PackageNotFoundError):
        # When: HTTPのUser-Agentを生成する
        user_agent = build_client_user_agent()
    # Then: 公開の__version__と同じフォールバックを使う
    assert user_agent == f"amivoice-api-client/0.0.0 Python/{sys.version_info.major}.{sys.version_info.minor}"


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize("proxy", [None, "http://user:password@proxy.test:8080"])
def test_http_recognition_request_user_agent_valid_return_headers(scheme: str, proxy: str | None) -> None:
    """HTTPとHTTPSで認識リクエストとCONNECTにUser-Agentを送る"""
    # Given: 呼び出し元が所有するヘッダと認証付きプロキシ設定
    headers = {"Authorization": "Bearer dummy", "Content-Type": "audio/wav"}
    with (
        patch("http.client.HTTPConnection") as http_factory,
        patch("http.client.HTTPSConnection") as https_factory,
        patch("amivoice._user_agent.version", return_value="1.2.3"),
    ):
        factory = https_factory if scheme == "https" else http_factory
        connection = factory.return_value
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b"{}"
        # When: 認識リクエストを送る
        HttpRecognitionConnection().request(
            f"{scheme}://example.test/v1/recognize", headers, b"audio", RecognitionParams(proxy_server_name=proxy)
        )
        # Then: 入力を変更せず、認識先と必要なCONNECTに同じ識別子を送る
        request_headers = connection.request.call_args.kwargs["headers"]
        assert request_headers["User-Agent"] == _EXPECTED_USER_AGENT
        assert request_headers["Authorization"] == "Bearer dummy"
        assert headers == {"Authorization": "Bearer dummy", "Content-Type": "audio/wav"}
        if proxy and scheme == "https":
            tunnel_headers = connection.set_tunnel.call_args.kwargs["headers"]
            assert tunnel_headers["User-Agent"] == _EXPECTED_USER_AGENT
            assert "Proxy-Authorization" in tunnel_headers
            assert "Proxy-Authorization" not in request_headers
        elif proxy:
            assert "Proxy-Authorization" in request_headers
        else:
            connection.set_tunnel.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_http_api_request_user_agent_valid_return_headers(method: str) -> None:
    """辞書・APIキー・感情パラメータの共通通信でUser-Agentを送る"""
    # Given: 認証ヘッダを受け取る補助APIの共通HTTPS接続
    headers = {"Authorization": "Bearer dummy"}
    with patch("http.client.HTTPSConnection") as factory, patch("amivoice._user_agent.version", return_value="1.2.3"):
        connection = factory.return_value
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b"{}"
        # When: 補助APIのリクエストを送る
        HttpApiConnection(30).request(method, "https://example.test/api", headers, None)
        # Then: 呼び出し元の認証ヘッダを維持し、入力を変更しない
        assert connection.request.call_args.kwargs["headers"] == {"User-Agent": _EXPECTED_USER_AGENT, **headers}
        assert headers == {"Authorization": "Bearer dummy"}


@pytest.mark.parametrize("scheme", ["ws", "wss"])
@pytest.mark.parametrize("proxy", [None, "http://user:password@proxy.test:8080"])
def test_websocket_connect_user_agent_valid_return_upgrade_and_tunnel_headers(scheme: str, proxy: str | None) -> None:
    """UpgradeとプロキシCONNECTで同じUser-Agentを送る"""
    # Given: RFC 6455のnonceに対応する正常なUpgrade応答
    upgrade = (
        b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        b"Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n"
    )
    with (
        patch("socket.create_connection") as factory,
        patch("ssl.create_default_context") as tls_context,
        patch("secrets.token_bytes", return_value=b"the sample nonce"),
        patch("amivoice._user_agent.version", return_value="1.2.3"),
    ):
        sock = factory.return_value
        tls_context.return_value.wrap_socket.return_value = sock
        sock.recv.side_effect = [b"HTTP/1.1 200 OK\r\n\r\n", upgrade] if proxy else [upgrade]
        connection = WebSocketConnection()
        try:
            # When: 直接又はプロキシ経由でWebSocketを接続する
            connection.connect(f"{scheme}://example.test/v1/", "dummy", RecognitionParams(proxy_server_name=proxy))
            # Then: すべてのハンドシェイクで識別子を送るがプロキシ認証を認識先に送らない
            requests = [call.args[0] for call in sock.sendall.call_args_list]
            assert len(requests) == (2 if proxy else 1)
            for request in requests:
                assert f"User-Agent: {_EXPECTED_USER_AGENT}\r\n".encode() in request
            assert b"Authorization: Bearer dummy\r\n" in requests[-1]
            assert b"Proxy-Authorization:" not in requests[-1]
            if proxy:
                assert b"Proxy-Authorization:" in requests[0]
        finally:
            connection.close()
