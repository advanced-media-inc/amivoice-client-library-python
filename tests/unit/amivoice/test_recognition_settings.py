"""認識設定オブジェクトの公開契約"""

import inspect
from dataclasses import FrozenInstanceError, fields
from typing import get_type_hints
from unittest.mock import Mock

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


def test_settings_none_override_invalid_raise_ConfigurationError() -> None:
    """設定オブジェクト自体のNoneを拒否する"""
    # Given: 既定の認識設定
    base = RecognitionSettings(grammar_file_names="-a-general", logging_opt_out=True)
    # When / Then: 全体の解除ではなく型のエラーにする
    with pytest.raises(ConfigurationError, match=r"^settings must be RecognitionSettings or USE_CLIENT_DEFAULT$"):
        merge_recognition_settings(base, None)


@pytest.mark.parametrize("method_name", ["transcribe", "stream", "submit"])
def test_recognition_none_settings_invalid_raise_ConfigurationError(method_name: str) -> None:
    """各認識メソッドは通信を開始せずNoneを拒否する"""
    # Given: 必須設定とログ保存拒否を保持したクライアント
    transport = Mock()
    settings = RecognitionSettings(grammar_file_names="-a-general", logging_opt_out=True)
    client = (
        AmiVoiceAsyncClient("key", settings=settings, transport=transport)
        if method_name == "submit"
        else AmiVoiceClient("key", settings=settings, hrp_transport=transport, wrp_transport=transport)
    )
    method = getattr(client, method_name)
    audio = () if method_name == "stream" else (b"audio",)
    # When / Then: 呼び出し直後に設定エラーとなり送信も接続も行わない
    with pytest.raises(ConfigurationError, match=r"^settings must be RecognitionSettings or USE_CLIENT_DEFAULT$"):
        method(*audio, settings=None)
    assert transport.mock_calls == []
    assert client._settings == settings


@pytest.mark.parametrize("client_type", [AmiVoiceClient, AmiVoiceAsyncClient])
@pytest.mark.parametrize("kwargs", [{}, {"settings": None}])
def test_client_empty_settings_valid_return_empty_defaults(client_type: type, kwargs: dict[str, object]) -> None:
    """コンストラクタの省略とNoneは空の認識設定として受け付ける"""
    # Given: 未指定又はNoneの認識設定
    # When: クライアントを生成する
    client = client_type("key", **kwargs)
    # Then: 空設定として初期化できる
    assert client._settings == RecognitionSettings()


@pytest.mark.parametrize("settings", [None, USE_CLIENT_DEFAULT, "bad", 0, False, {}])
def test_transcribe_invalid_settings_invalid_raise_ConfigurationError(settings: object) -> None:
    """モジュール関数は認識設定オブジェクト以外を通信前に拒否する"""
    # Given: 不正な認識設定と送信を監視するtransport
    transport = Mock()
    # When / Then: 設定の型エラーとなり通信しない
    with pytest.raises(ConfigurationError, match=r"^settings must be RecognitionSettings$"):
        transcribe(b"audio", settings=settings, api_key="key", _transport=transport)
    assert transport.mock_calls == []


def test_transcribe_empty_settings_invalid_raise_missing_grammar_ConfigurationError() -> None:
    """空の設定オブジェクトは従来どおり必須項目不足で拒否する"""
    # Given: 空設定と送信を監視するtransport
    transport = Mock()
    # When / Then: 設定の型は受け付け必須項目を検証する
    with pytest.raises(ConfigurationError, match="grammar_file_names is required"):
        transcribe(b"audio", settings=RecognitionSettings(), api_key="key", _transport=transport)
    assert transport.mock_calls == []


def test_transcribe_settings_annotation_valid_return_required_non_nullable_type() -> None:
    """モジュール関数の認識設定は必須でNoneを含めない"""
    # Given: モジュール関数の型ヒントとシグネチャ
    annotation = get_type_hints(transcribe)["settings"]
    parameter = inspect.signature(transcribe).parameters["settings"]
    # When / Then: 設定オブジェクトの明示指定を要求する
    assert annotation is RecognitionSettings
    assert parameter.default is inspect.Parameter.empty


def test_transcribe_missing_settings_invalid_raise_TypeError() -> None:
    """モジュール関数の設定を省略した場合は必須引数エラーになる"""
    # Given: 設定引数のない呼び出し
    # When / Then: 関数本体の実行前に引数不足を拒否する
    with pytest.raises(TypeError, match="settings"):
        transcribe(b"audio", api_key="key")


@pytest.mark.parametrize("target", [AmiVoiceClient.transcribe, AmiVoiceClient.stream, AmiVoiceAsyncClient.submit])
def test_recognition_settings_annotation_valid_return_non_nullable_type(target: object) -> None:
    """呼び出し時の型ヒントにNoneを含めない"""
    # Given: 各認識メソッドの型ヒント
    annotation = get_type_hints(target)["settings"]
    # When / Then: 受け付ける設定型とsentinel型だけを公開する
    assert annotation == RecognitionSettings | type(USE_CLIENT_DEFAULT)


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
