"""標準 HTTP クライアントによる HRP 認識のテスト"""

import http.client
from unittest.mock import MagicMock, patch

import pytest

from amivoice._http_recognition import HttpRecognitionTransport
from amivoice._params import RecognitionParams
from amivoice.exceptions import AuthenticationError, ConnectionFailedError, RecognitionError


def _http_connection(body: bytes = b'{"text":"hello"}\r\n', status: int = 200) -> MagicMock:
    """HTTP レスポンスを持つ接続を生成する"""
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = status
    response.read.return_value = body
    response.headers.get_content_charset.return_value = "UTF-8"
    response.getheader.return_value = "session-id"
    return connection


def test_http_transcribe_timeouts_valid_return_last_final_result() -> None:
    """接続と受信のタイムアウトを別々に設定する"""
    # Given: 途中結果と複数の確定結果
    connection = _http_connection(b'{"text":"first"}\r\n{"text":"partial..."}\r\n{"text":"last"}\r\n')
    params = RecognitionParams(connect_timeout=1000, receive_timeout=2000)
    # When: 標準ライブラリの接続境界をモックして認識する
    with patch("amivoice._http_connection.http.client.HTTPSConnection", return_value=connection) as factory:
        result = HttpRecognitionTransport().transcribe("https://example.com/recognize?x=1", "key", params, b"audio")
    # Then: 最後の確定結果、session ID、別々の秒数を保持する
    assert result.text == "last"
    assert result.session_id == "session-id"
    assert factory.call_args.kwargs["timeout"] == 1.0
    connection.sock.settimeout.assert_called_once_with(2.0)
    assert connection.request.call_args.args[:2] == ("POST", "/recognize?x=1")
    connection.close.assert_called_once()


@pytest.mark.parametrize(("status", "error"), [(401, AuthenticationError), (403, AuthenticationError), (500, RecognitionError)])
def test_http_transcribe_status_invalid_raise_public_error(status: int, error: type[Exception]) -> None:
    """HTTP エラーを公開例外へ変換し接続を閉じる"""
    # Given: エラーステータス
    connection = _http_connection(status=status)
    # When / Then: エラーでも接続を閉じる
    with patch("amivoice._http_connection.http.client.HTTPSConnection", return_value=connection), pytest.raises(error):
        HttpRecognitionTransport().transcribe("https://example.com/", "key", RecognitionParams(), b"audio")
    connection.close.assert_called_once()


@pytest.mark.parametrize("body", [b"", b"broken", b"[]", b'{"text":"unfinished..."}\r\n'])
def test_http_transcribe_response_invalid_raise_RecognitionError(body: bytes) -> None:
    """結果がない場合と不正 JSON を拒否する"""
    # Given: 不正な本文
    connection = _http_connection(body)
    # When / Then: 待機せず RecognitionError を送出する
    with patch("amivoice._http_connection.http.client.HTTPSConnection", return_value=connection), pytest.raises(RecognitionError):
        HttpRecognitionTransport().transcribe("https://example.com/", "key", RecognitionParams(), b"audio")
    connection.close.assert_called_once()


@pytest.mark.parametrize(
    ("phase", "error"), [("connect", ConnectionFailedError), ("request", RecognitionError), ("getresponse", RecognitionError)]
)
def test_http_transcribe_network_failure_invalid_raise_public_error(phase: str, error: type[Exception]) -> None:
    """失敗フェーズで例外を区別して後始末する"""
    # Given: 通信途中の失敗
    connection = _http_connection()
    getattr(connection, phase).side_effect = http.client.HTTPException("failure")
    # When / Then: 元の例外を公開例外へ変換する
    with patch("amivoice._http_connection.http.client.HTTPSConnection", return_value=connection), pytest.raises(error):
        HttpRecognitionTransport().transcribe("https://example.com/", "key", RecognitionParams(), b"audio")
    connection.close.assert_called_once()


def test_http_transcribe_proxy_valid_return_tunneled_request() -> None:
    """認証付きプロキシ経由でもオリジンにプロキシ認証を送らない"""
    # Given: 接続先とプロキシを分ける
    connection = _http_connection()
    params = RecognitionParams(proxy_server_name="user:pass@proxy.example:8080")
    # When: HTTPS の CONNECT トンネルを設定する
    with patch("amivoice._http_connection.http.client.HTTPSConnection", return_value=connection) as factory:
        HttpRecognitionTransport().transcribe("https://example.com/", "key", params, b"audio")
    # Then: 認証は CONNECT ヘッダーだけに含める
    assert factory.call_args.args == ("proxy.example", 8080)
    connection.set_tunnel.assert_called_once_with("example.com", 443, headers={"Proxy-Authorization": "Basic dXNlcjpwYXNz"})
    assert "Proxy-Authorization" not in connection.request.call_args.kwargs["headers"]
