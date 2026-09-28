"""音声フォーマット名と接続エンジン名の定数のテスト。"""

import pytest

from amivoice import Codec, Engine


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8k", Codec.HEADER_8K),
        ("16k", Codec.HEADER_16K),
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


def test_engine_values_valid_match_supported_engine_names() -> None:
    """Enginesの公式エンジン名定数が正しい値を持つことを確認する。"""
    # Given: 公式ドキュメントに記載された接続エンジン名
    expected_values = {
        "A2_JA_GENERAL": "-a2-ja-general",
        "A2_ZH_GENERAL": "-a2-zh-general",
        "A2_MULTI_GENERAL": "-a2-multi-general",
        "A2B_JA_GENERAL": "-a2b-ja-general",
        "A2B_ZH_GENERAL": "-a2b-zh-general",
        "A2B_MULTI_GENERAL": "-a2b-multi-general",
        "A_GENERAL": "-a-general",
        "A_MEDICAL": "-a-medical",
        "A_BIZFINANCE": "-a-bizfinance",
        "A_BIZINSURANCE": "-a-bizinsurance",
        "A_GENERAL_EN": "-a-general-en",
        "A_GENERAL_ZH": "-a-general-zh",
        "A_GENERAL_KO": "-a-general-ko",
        "A_GENERAL_INPUT": "-a-general-input",
        "A_MEDICAL_INPUT": "-a-medical-input",
        "A_BIZINSURANCE_INPUT": "-a-bizinsurance-input",
        "A_BIZFINANCE_INPUT": "-a-bizfinance-input",
        "A_NAME_INPUT_PRIVATE": "-a-name-input-private",
        "A_ADDRESS_INPUT_PRIVATE": "-a-address-input-private",
        "A_RULE_INPUT_PRIVATE": "-a-rule-input-private",
    }

    # When: Enginesの各定数を参照する
    actual_values = {name: getattr(Engine, name) for name in expected_values}

    # Then: 公式エンジン名と一致する
    assert actual_values == expected_values


@pytest.mark.parametrize("name", ["E2E_JA_GENERAL", "HYBRID_GENERAL", "PRIVATE_RULE_INPUT"])
def test_engine_alias_name_invalid_raise_AttributeError(name: str) -> None:
    """Enginesが接続エンジン名から導けない別名を持たないことを確認する。"""
    # Given: 接続エンジン名から導けない以前の別名
    # When / Then: 別名を参照できない
    with pytest.raises(AttributeError):
        getattr(Engine, name)


def test_engine_member_valid_return_str_value() -> None:
    """Engineの各定数が接続エンジン名の文字列として扱えることを確認する。"""
    # Given: 会話_汎用エンジンの定数
    engine = Engine.A_GENERAL

    # When: 文字列として展開する
    formatted = f"{engine}"

    # Then: 接続エンジン名の文字列と一致する
    assert isinstance(engine, str)
    assert engine == "-a-general"
    assert formatted == "-a-general"
    assert Engine("-a-general") is Engine.A_GENERAL


def test_engine_member_reassign_invalid_raise_AttributeError() -> None:
    """Engineの定数を書き換えられないことを確認する。"""
    # Given: 定義済みのEngine定数
    # When / Then: 再代入が拒否される
    with pytest.raises(AttributeError):
        Engine.A_GENERAL = "-bogus"  # type: ignore[misc]

    assert Engine.A_GENERAL == "-a-general"
