"""モジュールレベルの同期認識を公開境界で確認する"""

from unittest.mock import MagicMock

import pytest

from amivoice import Codec, Engine, RecognitionSettings, transcribe
from amivoice.exceptions import ConfigurationError


def test_transcribe_official_parameters_valid_return_result() -> None:
    """便利関数も公式形式を直接生成する"""
    # Given: HTTPレスポンスを返す注入処理
    transport = MagicMock()
    transport.request.return_value = (200, b'{"text":"hello","code":"","message":""}')
    # When: 型付き定数と設定を渡す
    result = transcribe(
        b"audio",
        api_key="dummy",
        settings=RecognitionSettings(
            grammar_file_names=Engine.A_GENERAL, codec=Codec.LSB16K, selected_channel=1, logging_opt_out=True
        ),
        _transport=transport,
    )
    # Then: 認識結果と公式multipartパートを確認する
    assert result.text == "hello"
    assert transport.request.call_args.args[0] == "https://acp-api.amivoice.com/v1/nolog/recognize"
    assert b'name="c"\r\n\r\nLSB16K' in transport.request.call_args.args[2]


@pytest.mark.parametrize("name", ["mode", "result_type", "domain_id", "voice_detection"])
def test_transcribe_removed_argument_invalid_raise_TypeError(name: str) -> None:
    """削除した引数を黙って受け付けない"""
    # Given: 非公式設定
    # When / Then: Pythonの引数検証で拒否する
    with pytest.raises(TypeError):
        transcribe(
            b"audio", api_key="dummy", settings=RecognitionSettings(grammar_file_names=Engine.A_GENERAL), **{name: "value"}
        )


def test_transcribe_engine_missing_invalid_raise_ConfigurationError() -> None:
    """必須エンジン名は通信前に検証する"""
    # Given: 通信処理
    transport = MagicMock()
    # When / Then: 設定不足で通信しない
    with pytest.raises(ConfigurationError, match="grammar_file_names"):
        transcribe(b"audio", api_key="dummy", settings=RecognitionSettings(), _transport=transport)
    transport.request.assert_not_called()
