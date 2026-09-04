"""使用量集計タグヘルパーのユニットテスト"""

import pytest

from amivoice import build_billing_extension
from amivoice._billing import resolve_billing_extension
from amivoice._params import RecognitionParams
from amivoice.exceptions import ConfigurationError


def test_build_billing_extension_billing_key_valid_return_compact_json() -> None:
    """billing_key から空白のない JSON 文字列を生成することを確認する"""
    # Given: 使用量集計タグ
    billing_key = "user01"

    # When: billing_key 専用ヘルパーを呼び出す
    extension = build_billing_extension(billing_key)

    # Then: AmiVoice API が受け取るコンパクト JSON が返る
    assert extension == '{"client_info":{"billing_key":"user01"}}'


def test_build_billing_extension_japanese_billing_key_valid_return_utf8_json() -> None:
    """日本語の billing_key が JSON にそのまま含まれることを確認する"""
    # Given: 日本語を含む使用量集計タグ
    billing_key = "部署A"

    # When: billing_key 専用ヘルパーを呼び出す
    extension = build_billing_extension(billing_key)

    # Then: Unicode エスケープされずに JSON に含まれる
    assert extension == '{"client_info":{"billing_key":"部署A"}}'


def test_build_billing_extension_empty_billing_key_invalid_raise_ConfigurationError() -> None:
    """空文字の billing_key で ConfigurationError が送出されることを確認する"""
    # Given: 空の使用量集計タグ
    # When / Then: JSON 生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="billing_key"):
        build_billing_extension("")


def test_recognition_params_extension_and_billing_key_invalid_raise_ConfigurationError() -> None:
    """Extension と billing_key の同時指定で ConfigurationError が送出されることを確認する"""
    # Given: 既存 extension と専用 billing_key
    # When / Then: 認識パラメータの生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="extension and billing_key"):
        RecognitionParams(extension="legacy-extension", billing_key="user01")


def test_resolve_billing_extension_billing_key_valid_return_generated_extension() -> None:
    """billing_key が指定された場合に extension JSON が生成されることを確認する"""
    # Given: 専用 billing_key
    # When: extension の解決を実行する
    extension = resolve_billing_extension(None, "user01")

    # Then: 専用形式の extension が返る
    assert extension == '{"client_info":{"billing_key":"user01"}}'


def test_resolve_billing_extension_extension_valid_return_unchanged() -> None:
    """既存 extension が指定された場合に値が維持されることを確認する"""
    # Given: 既存形式の extension
    # When: extension の解決を実行する
    extension = resolve_billing_extension("legacy-extension", None)

    # Then: 既存の extension がそのまま返る
    assert extension == "legacy-extension"


@pytest.mark.parametrize("billing_key", [""])
def test_recognition_params_empty_billing_key_invalid_raise_ConfigurationError(billing_key: str) -> None:
    """空文字の billing_key を認識パラメータへ設定すると ConfigurationError が送出されることを確認する"""
    # Given: 不正な billing_key
    # When / Then: 認識パラメータの生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="billing_key"):
        RecognitionParams(billing_key=billing_key)
