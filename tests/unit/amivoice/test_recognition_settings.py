"""認識設定オブジェクトの公開契約"""

import inspect
from dataclasses import FrozenInstanceError, fields

import pytest

from amivoice import (
    USE_CLIENT_DEFAULT,
    AmiVoiceAsyncClient,
    AmiVoiceClient,
    ConfigurationError,
    ProfileWord,
    RecognitionSettings,
    SegmenterProperties,
    transcribe,
)
from amivoice._params import RecognitionParams
from amivoice._recognition_settings import merge_recognition_settings, settings_to_params


def test_settings_override_valid_return_inherited_and_cleared_values() -> None:
    """未指定は継承しNoneで解除しFalseと0を保持する"""
    # Given: クライアント既定の設定
    base = RecognitionSettings(grammar_file_names="-a-general", profile_id=":test")
    # When: 呼び出し単位の上書きを解決する
    configured = merge_recognition_settings(
        base, RecognitionSettings(profile_id=None, keep_filler_token=False, max_decoding_time=0)
    )
    params = settings_to_params(configured, RecognitionParams())
    # Then: 個々の設定の意味を維持する
    assert params.grammar_file_names == "-a-general"
    assert params.profile_id is None
    assert params.keep_filler_token is False
    assert params.max_decoding_time == 0
    assert RecognitionSettings().codec is USE_CLIENT_DEFAULT


@pytest.mark.parametrize("override", [USE_CLIENT_DEFAULT, RecognitionSettings()])
def test_settings_empty_override_valid_return_client_defaults(override: object) -> None:
    """空の差分とsentinelはいずれも既定設定を継承する"""
    # Given: 既定設定
    base = RecognitionSettings(codec="LSB16K", logging_opt_out=True)
    # When: 空の指定を適用する
    resolved = merge_recognition_settings(base, override)
    # Then: 既定設定は変わらない
    assert resolved == base


def test_settings_none_override_valid_return_cleared_settings() -> None:
    """オブジェクト自体のNoneは全認識設定を解除する"""
    # Given: 既定の認識設定
    base = RecognitionSettings(grammar_file_names="-a-general", logging_opt_out=True)
    # When: 全体を解除する
    cleared = merge_recognition_settings(base, None)
    # Then: 既定設定と通信設定は別に扱う
    assert cleared == RecognitionSettings()
    params = settings_to_params(cleared, RecognitionParams(connect_timeout=10))
    assert params.grammar_file_names is None
    assert params.connect_timeout == 10


@pytest.mark.parametrize(
    ("base", "override", "expected"),
    [
        (
            RecognitionSettings(segmenter=SegmenterProperties(pre_time=100)),
            RecognitionSettings(segmenter_properties="threshold=6000"),
            "threshold=6000",
        ),
        (
            RecognitionSettings(segmenter_properties="threshold=5000"),
            RecognitionSettings(segmenter=SegmenterProperties(pre_time=200)),
            "preTime=200",
        ),
    ],
)
def test_settings_alternative_override_valid_return_replaced_parameter(
    base: RecognitionSettings, override: RecognitionSettings, expected: str
) -> None:
    """型付き設定とraw設定を切り替えても既定値と競合しない"""
    # Given: 一方の形式を使う既定設定
    # When: 別形式へ切り替える
    resolved = merge_recognition_settings(base, override)
    # Then: 今回の形式だけが送信される
    assert settings_to_params(resolved, RecognitionParams()).segmenter_properties == expected


def test_settings_sequence_valid_return_immutable_snapshot() -> None:
    """単語一覧の外部変更が設定に影響しない"""
    # Given: 可変の単語一覧
    words = [ProfileWord("one", "わん")]
    settings = RecognitionSettings(profile_words=words)
    # When: 元の一覧を変更する
    words.clear()
    # Then: 作成時の設定を保持する
    assert settings.profile_words == (ProfileWord("one", "わん"),)
    with pytest.raises(FrozenInstanceError):
        settings.profile_id = ":other"


@pytest.mark.parametrize("client_type", [AmiVoiceClient, AmiVoiceAsyncClient])
@pytest.mark.parametrize("settings", ["bad", 0, False, {}])
def test_client_invalid_settings_invalid_raise_ConfigurationError(client_type: type, settings: object) -> None:
    """不正な設定オブジェクトを送信前に拒否する"""
    # Given: 型付き設定ではない値
    # When / Then: コンストラクタで拒否する
    with pytest.raises(ConfigurationError):
        client_type("key", settings=settings)


@pytest.mark.parametrize(
    "target",
    [
        AmiVoiceClient,
        AmiVoiceClient.transcribe,
        AmiVoiceClient.stream,
        transcribe,
        AmiVoiceAsyncClient,
        AmiVoiceAsyncClient.submit,
    ],
)
def test_api_settings_valid_return_single_recognition_argument(target: object) -> None:
    """認識設定項目を各エントリポイントに重複定義しない"""
    # Given: 公開API
    parameters = inspect.signature(target).parameters
    # When: 設定項目と比較する
    names = {field.name for field in fields(RecognitionSettings)}
    # Then: 設定は1つの引数へ集約し通信設定は維持する
    assert "settings" in parameters
    assert names.isdisjoint(parameters)
    assert {"proxy_server_name", "connect_timeout", "receive_timeout"} <= parameters.keys()
