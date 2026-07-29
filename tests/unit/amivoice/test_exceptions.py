# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownMemberType=false

"""exceptions モジュールのユニットテスト。"""

import pytest

from amivoice.exceptions import (
    AmiVoiceError,
    AuthenticationError,
    ConfigurationError,
    RecognitionError,
)
from amivoice.exceptions import (
    ConnectionFailedError as AmiConnectionError,
)
from amivoice.models import RecognitionResult


@pytest.mark.parametrize(
    "exception_type",
    [AuthenticationError, AmiConnectionError, RecognitionError, ConfigurationError],
)
def test_exception_type_all_subtypes_valid_extend_AmiVoiceError(
    exception_type: type[AmiVoiceError],
) -> None:
    """全てのサブ例外クラスが AmiVoiceError を継承することを確認する。"""
    # Given: 各サブ例外クラス（パラメトライズ）
    # When / Then: AmiVoiceError のサブクラスである
    assert issubclass(exception_type, AmiVoiceError)


def test_AmiVoiceError_base_class_valid_extend_Exception() -> None:
    """AmiVoiceError が Exception を継承することを確認する。"""
    # Given: AmiVoiceError クラス
    # When / Then: Exception のサブクラスである
    assert issubclass(AmiVoiceError, Exception)


@pytest.mark.parametrize(
    ("exception", "message"),
    [
        (AmiVoiceError("base error"), "base error"),
        (AuthenticationError("auth error"), "auth error"),
        (AmiConnectionError("connection error"), "connection error"),
        (RecognitionError("recognition error"), "recognition error"),
        (ConfigurationError("config error"), "config error"),
    ],
)
def test_exception_str_all_types_valid_return_message_string(exception: AmiVoiceError, message: str) -> None:
    """全ての例外クラスで str() がメッセージ文字列を返すことを確認する。"""
    # Given: 各例外インスタンスとメッセージ（パラメトライズ）
    # When: str() で文字列化する
    # Then: 生成時のメッセージが返る
    assert str(exception) == message


@pytest.mark.parametrize(
    "exception",
    [
        AuthenticationError("auth error"),
        AmiConnectionError("connection error"),
        RecognitionError("recognition error"),
        ConfigurationError("config error"),
    ],
)
def test_exception_subclass_all_subtypes_valid_caught_as_AmiVoiceError(
    exception: AmiVoiceError,
) -> None:
    """サブ例外クラスが AmiVoiceError として補足できることを確認する。"""
    # Given: 各サブ例外インスタンス（パラメトライズ）
    # When / Then: raise しても AmiVoiceError として補足される
    with pytest.raises(AmiVoiceError):
        raise exception


def test_RecognitionError_no_result_valid_return_none() -> None:
    """Result を省略した場合に result が None になることを確認する。"""
    # Given: result を指定しない RecognitionError
    # When: RecognitionError を生成する
    exc = RecognitionError("something went wrong")

    # Then: result が None
    assert exc.result is None


def test_RecognitionError_with_result_valid_return_result() -> None:
    """Result を渡した場合にそのまま格納されることを確認する。"""
    # Given: エラー状態の RecognitionResult
    result = RecognitionResult(raw='{"code": "E001"}', data={"code": "E001"}, is_error=True)

    # When: result を渡して RecognitionError を生成する
    exc = RecognitionError("E001", result=result)

    # Then: result が格納されており is_error が True
    assert exc.result is result
    assert exc.result.is_error is True
