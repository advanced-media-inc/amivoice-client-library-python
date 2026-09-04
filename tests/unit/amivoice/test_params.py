"""認識パラメータのユニットテスト。"""

import pytest

from amivoice._params import RecognitionParams, merge_params
from amivoice.exceptions import ConfigurationError


@pytest.mark.parametrize("value", [0.0, 0.3, 1.0])
def test_recognition_params_confidence_level_boundary_valid_return_params(value: float) -> None:
    """confidence_level の境界値を含む有効な値を保持できることを確認する。"""
    # Given: 有効な confidence_level
    # When: RecognitionParams を生成する
    params = RecognitionParams(confidence_level=value)

    # Then: 指定した値が保持される
    assert params.confidence_level == value


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan")])
def test_recognition_params_confidence_level_out_of_range_invalid_raise_ConfigurationError(value: float) -> None:
    """confidence_level が範囲外の場合に ConfigurationError が送出されることを確認する。"""
    # Given: 範囲外の confidence_level
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="confidence_level"):
        RecognitionParams(confidence_level=value)


def test_recognition_params_confidence_level_bool_invalid_raise_ConfigurationError() -> None:
    """confidence_level に bool を指定した場合に ConfigurationError が送出されることを確認する。"""
    # Given: int のサブクラスでもある bool の confidence_level
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="confidence_level"):
        RecognitionParams(confidence_level=True)  # type: ignore[arg-type]


def test_merge_params_confidence_level_override_invalid_raise_ConfigurationError() -> None:
    """呼び出し時の confidence_level override も検証されることを確認する。"""
    # Given: 既定値を持つ認識パラメータ
    base = RecognitionParams(confidence_level=0.3)

    # When / Then: override に不正値を指定すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="confidence_level"):
        merge_params(base, confidence_level=1.1)


def test_recognition_params_confidence_level_string_invalid_raise_ConfigurationError() -> None:
    """confidence_level に数値以外を指定した場合に ConfigurationError が送出されることを確認する。"""
    # Given: 文字列の confidence_level
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="confidence_level"):
        RecognitionParams(confidence_level="0.3")  # type: ignore[arg-type]
