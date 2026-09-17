"""音声コーデックと接続エンジン名の定数テスト。"""

import pytest

from amivoice import Codec


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8k", Codec.CODEC_8K),
        ("16k", Codec.CODEC_16K),
        ("lsb16k", Codec.LSB16K),
        ("MsB48K", Codec.MSB48K),
        ("mulaw", Codec.MULAW),
        ("AlAw", Codec.ALAW),
    ],
)
def test_codec_case_insensitive_value_valid_returns_member(value: str, expected: Codec) -> None:
    """Codecが音声フォーマットの大文字小文字を区別せず解決することを確認する。"""
    # Given: 大文字小文字を混在させた音声フォーマット名
    # When: Codecを値から生成する
    codec = Codec(value)

    # Then: 対応するCodecメンバーが返る
    assert codec is expected
    assert isinstance(codec, str)
    assert codec.value == expected.value


def test_codec_values_valid_include_all_supported_formats() -> None:
    """CodecがAPIの全音声フォーマットを保持することを確認する。"""
    # Given: APIで指定できる音声フォーマット名
    expected_values = {
        "8K",
        "16K",
        "LSB8K",
        "LSB11K",
        "LSB16K",
        "LSB22K",
        "LSB32K",
        "LSB44K",
        "LSB48K",
        "MSB8K",
        "MSB11K",
        "MSB16K",
        "MSB22K",
        "MSB32K",
        "MSB44K",
        "MSB48K",
        "MULAW",
        "ALAW",
    }

    # When: Codecの値を列挙する
    actual_values = {codec.value for codec in Codec}

    # Then: サポート対象と一致する
    assert actual_values == expected_values


def test_codec_invalid_value_raise_ValueError() -> None:
    """対応していない音声フォーマットでValueErrorが送出されることを確認する。"""
    # Given: 対応していない音声フォーマット名
    # When / Then: Codecの生成が拒否される
    with pytest.raises(ValueError):
        Codec("unknown")
