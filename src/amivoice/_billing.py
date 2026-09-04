"""使用量集計タグを AmiVoice API の extension 形式へ変換する内部ヘルパー"""

import json

from .exceptions import ConfigurationError


def _validate_billing_key(billing_key: str) -> None:
    """billing_key が空でない文字列であることを検証する"""
    if not isinstance(billing_key, str) or billing_key == "":
        raise ConfigurationError("Invalid billing_key: must be a non-empty string")


def build_billing_extension(billing_key: str) -> str:
    """使用量集計タグからコンパクトな extension JSON を生成する。

    Args:
        billing_key (str): 使用量集計に使用する任意の文字列

    Returns:
        str: ``client_info.billing_key`` を含むコンパクトな JSON 文字列

    Raises:
        ConfigurationError: ``billing_key`` が空文字または文字列でない場合
    """
    _validate_billing_key(billing_key)
    return json.dumps(
        {"client_info": {"billing_key": billing_key}},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def resolve_billing_extension(extension: str | None, billing_key: str | None) -> str | None:
    """既存 extension と billing_key の設定を解決する。

    Args:
        extension (str | None): 既存の extension 文字列
        billing_key (str | None): 専用の使用量集計タグ

    Returns:
        str | None: トランスポートへ渡す extension 文字列、または ``None``

    Raises:
        ConfigurationError: ``extension`` と ``billing_key`` を同時指定した場合、または
            ``billing_key`` が空文字もしくは文字列でない場合
    """
    if extension is not None and billing_key is not None:
        raise ConfigurationError("extension and billing_key cannot be specified together")
    if billing_key is None:
        return extension
    return build_billing_extension(billing_key)
