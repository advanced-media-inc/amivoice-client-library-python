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


@pytest.mark.parametrize("field_name", ["max_decoding_time", "max_response_time", "target_response_time"])
def test_recognition_params_processing_time_negative_invalid_raise_ConfigurationError(field_name: str) -> None:
    """処理時間パラメータに負値を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 負の処理時間パラメータ
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match=field_name):
        RecognitionParams(**{field_name: -1})


@pytest.mark.parametrize("field_name", ["max_decoding_time", "max_response_time", "target_response_time"])
def test_recognition_params_processing_time_non_negative_valid_return_params(field_name: str) -> None:
    """処理時間パラメータに非負整数を指定できることを確認する"""
    # Given: 0 の処理時間パラメータ
    # When: RecognitionParams を生成する
    params = RecognitionParams(**{field_name: 0})

    # Then: 指定した値が保持される
    assert getattr(params, field_name) == 0


@pytest.mark.parametrize("field_name", ["max_decoding_time", "max_response_time", "target_response_time"])
@pytest.mark.parametrize("value", [0.5, "1"], ids=["fractional", "string"])
def test_recognition_params_processing_time_non_integer_invalid_raise_ConfigurationError(field_name: str, value: object) -> None:
    """処理時間パラメータに整数以外を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 整数以外の処理時間パラメータ
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match=field_name):
        RecognitionParams(**{field_name: value})  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["max_decoding_rate", "target_decoding_rate"])
def test_recognition_params_processing_rate_negative_valid_return_params(field_name: str) -> None:
    """処理レートパラメータの負値を無効指定として許容することを確認する"""
    # Given: 無効指定を表す負の処理レート
    # When: RecognitionParams を生成する
    params = RecognitionParams(**{field_name: -1.0})

    # Then: 指定した負値が保持される
    assert getattr(params, field_name) == -1.0


@pytest.mark.parametrize(
    "field_name",
    [
        "max_decoding_time",
        "max_response_time",
        "max_decoding_rate",
        "target_response_time",
        "target_decoding_rate",
    ],
)
def test_recognition_params_processing_parameter_bool_invalid_raise_ConfigurationError(field_name: str) -> None:
    """処理時間制御パラメータに bool を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: bool の処理時間制御パラメータ
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match=field_name):
        RecognitionParams(**{field_name: True})  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["max_decoding_rate", "target_decoding_rate"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")], ids=["nan", "positive_inf", "negative_inf"])
def test_recognition_params_processing_rate_non_finite_invalid_raise_ConfigurationError(field_name: str, value: float) -> None:
    """処理レートパラメータに非有限値を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 非有限の処理レートパラメータ
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match=field_name):
        RecognitionParams(**{field_name: value})


def test_recognition_params_processing_rate_non_numeric_invalid_raise_ConfigurationError() -> None:
    """処理レートパラメータに数値以外を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 文字列の処理レートパラメータ
    # When / Then: RecognitionParams の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="max_decoding_rate"):
        RecognitionParams(max_decoding_rate="1.0")  # type: ignore[arg-type]


def test_merge_params_processing_time_override_negative_invalid_raise_ConfigurationError() -> None:
    """処理時間パラメータの override に負値を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 既定値を持つ認識パラメータ
    base = RecognitionParams(max_decoding_time=1000)

    # When / Then: override に負値を指定すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="max_decoding_time"):
        merge_params(base, max_decoding_time=-1)


@pytest.mark.parametrize("value", [0, 5000])
def test_recognition_params_complete_timeout_non_negative_valid_return_params(value: int) -> None:
    """complete_timeout に非負整数を指定できることを確認する"""
    # Given: 非負の complete_timeout
    # When: RecognitionParams を生成する
    params = RecognitionParams(complete_timeout=value)

    # Then: 指定した値が保持される
    assert params.complete_timeout == value


def test_recognition_params_complete_timeout_negative_invalid_raise_ConfigurationError() -> None:
    """complete_timeout に負値を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 負の complete_timeout

    # When: RecognitionParams を生成する
    with pytest.raises(ConfigurationError, match="complete_timeout"):
        RecognitionParams(complete_timeout=-1)

    # Then: ConfigurationError が送出される


@pytest.mark.parametrize("value", [0.0, 2.0, 6.0, 7.5])
def test_recognition_params_wildcard_model_penalty_non_negative_valid_return_params(value: float) -> None:
    """wildcard_model_penalty は目安範囲外の非負値も保持できることを確認する"""
    # Given: 非負の wildcard_model_penalty
    # When: RecognitionParams を生成する
    params = RecognitionParams(wildcard_model_penalty=value)

    # Then: 指定した値が保持される
    assert params.wildcard_model_penalty == value


def test_recognition_params_wildcard_model_penalty_negative_invalid_raise_ConfigurationError() -> None:
    """wildcard_model_penalty に負値を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 負の wildcard_model_penalty

    # When: RecognitionParams を生成する
    with pytest.raises(ConfigurationError, match="wildcard_model_penalty"):
        RecognitionParams(wildcard_model_penalty=-0.1)

    # Then: ConfigurationError が送出される


@pytest.mark.parametrize("field_name", ["complete_timeout", "wildcard_model_penalty"])
def test_recognition_params_rule_grammar_parameter_bool_invalid_raise_ConfigurationError(field_name: str) -> None:
    """ルールグラマ専用パラメータに bool を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: bool のルールグラマ専用パラメータ

    # When: RecognitionParams を生成する
    with pytest.raises(ConfigurationError, match=field_name):
        RecognitionParams(**{field_name: True})  # type: ignore[arg-type]

    # Then: ConfigurationError が送出される


def test_merge_params_rule_grammar_parameter_override_invalid_raise_ConfigurationError() -> None:
    """ルールグラマ専用パラメータの override も検証されることを確認する"""
    # Given: ルールグラマ専用パラメータを持つ既定値
    base = RecognitionParams(complete_timeout=1000, wildcard_model_penalty=2.5)

    # When: 負値でパラメータを上書きする
    with pytest.raises(ConfigurationError, match="complete_timeout"):
        merge_params(base, complete_timeout=-1)

    # Then: ConfigurationError が送出される
