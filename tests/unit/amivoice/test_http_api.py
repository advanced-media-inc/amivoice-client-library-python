"""共通HTTPS通信の証明書検証と接続回収を確認する"""

import ssl
from unittest.mock import patch

from amivoice._http_api import HttpApiConnection


def test_http_api_tls_context_valid_require_certificate_verification() -> None:
    """TLSの証明書検証とホスト名照合を必ず有効にする"""
    # Given: 接続部分を記録するモック
    with patch("http.client.HTTPSConnection") as factory:
        connection = factory.return_value
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read.return_value = b"{}"
        # When: HTTPS APIを呼び出す
        HttpApiConnection(30.0).request("GET", "https://example.test/profilewords/engine/?adf=8k", {}, None)
        # Then: 安全なSSLContextを明示し接続を回収する
        context = factory.call_args.kwargs["context"]
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is True
        connection.close.assert_called_once()
