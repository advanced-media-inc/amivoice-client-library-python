"""通信先とプロキシの設定を検証するテスト"""

import base64

from amivoice._connection_settings import parse_http_proxy


def test_parse_http_proxy_encoded_credentials_valid_decode_before_basic_auth() -> None:
    """URLエスケープした認証情報をBasic認証前にデコードする"""
    # Given: ユーザー名とパスワードに予約文字を含むプロキシURL
    proxy = parse_http_proxy("http://user%40example:p%3Ass@proxy.example:8080")

    # When: Proxy-AuthorizationヘッダーのBasic認証情報を復号する
    assert proxy is not None
    encoded_credentials = proxy[2]["Proxy-Authorization"].removeprefix("Basic ")
    credentials = base64.b64decode(encoded_credentials).decode()

    # Then: 元のユーザー名とパスワードを認証情報として使う
    assert credentials == "user@example:p:ss"
