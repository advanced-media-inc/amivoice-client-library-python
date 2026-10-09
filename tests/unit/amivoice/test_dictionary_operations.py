"""辞書のプロファイル一覧と公式adf指定のテスト"""

from unittest.mock import MagicMock

import pytest

from amivoice import UserDictionaryClient
from amivoice.exceptions import ConfigurationError, DictionaryApiError


@pytest.mark.parametrize("sampling_rate,suffix", [(None, "/"), ("8k", "/?adf=8k"), ("16k", "/?adf=16k")])
def test_list_profiles_sampling_rate_valid_return_names(sampling_rate: str | None, suffix: str) -> None:
    """プロファイル一覧は末尾スラッシュと任意adfで取得する"""
    # Given: 一覧を返す通信処理
    transport = MagicMock()
    transport.request.return_value = (200, b'{"profileids":["sample","test"]}')
    client = UserDictionaryClient(api_key="dummy", transport=transport)
    # When: 一覧を取得する
    result = client.list_profiles("-a-general", sampling_rate=sampling_rate)
    # Then: 認証はヘッダで送る
    assert result == ("sample", "test")
    assert transport.request.call_args.args == (
        "GET",
        "https://acp-api.amivoice.com/profilewords/-a-general" + suffix,
        {"Authorization": "Bearer dummy"},
        None,
    )


def test_list_classnames_sampling_rate_valid_send_adf() -> None:
    """8kエンジンのクラス名を明示指定できる"""
    # Given: 空のクラス名一覧
    transport = MagicMock()
    transport.request.return_value = (200, b'{"classnames":[]}')
    client = UserDictionaryClient(api_key="dummy", transport=transport)
    # When: 8k対象で取得する
    assert client.list_classnames("-a-general", sampling_rate="8k") == ()
    # Then: 公式adfだけがクエリに入る
    assert transport.request.call_args.args[1] == "https://acp-api.amivoice.com/classnames/-a-general?adf=8k"


@pytest.mark.parametrize("method", ["list_profiles", "list_classnames", "get_words"])
def test_dictionary_sampling_rate_invalid_raise_ConfigurationError(method: str) -> None:
    """任意値や認証情報をadfに送らない"""
    # Given: 不正なサンプリングレート
    transport = MagicMock()
    client = UserDictionaryClient(api_key="dummy", transport=transport)
    # When / Then: 送信前に拒否する
    args = ("-a-general", "test") if method == "get_words" else ("-a-general",)
    with pytest.raises(ConfigurationError, match="sampling_rate"):
        getattr(client, method)(*args, sampling_rate="48k")
    transport.request.assert_not_called()


@pytest.mark.parametrize("body", [b"{}", b'{"profileids":[1]}', b'{"profileids":"test"}'])
def test_list_profiles_malformed_response_invalid_raise_DictionaryApiError(body: bytes) -> None:
    """応答の型が公式JSON構造と異なる場合は拒否する"""
    # Given: 不正なプロファイル一覧
    transport = MagicMock()
    transport.request.return_value = (200, body)
    client = UserDictionaryClient(api_key="dummy", transport=transport)
    # When / Then: 成功とみなさない
    with pytest.raises(DictionaryApiError):
        client.list_profiles("-a-general")


@pytest.mark.parametrize(
    "base_url", ["https://dummy:secret@example.test", "https://example.test?u=dummy", "https://example.test#fragment"]
)
def test_dictionary_base_url_credentials_invalid_raise_ConfigurationError(base_url: str) -> None:
    """認証情報をURLへ送らない"""
    # Given: 認証情報等を含む接続先
    # When / Then: URLを検証する
    with pytest.raises(ConfigurationError):
        UserDictionaryClient(api_key="dummy", base_url=base_url)
