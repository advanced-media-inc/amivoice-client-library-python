"""非同期HTTP感情分析の設定・送信・結果解析の契約を検証する"""

import inspect

import pytest

from amivoice import USE_CLIENT_DEFAULT, AmiVoiceAsyncClient, AmiVoiceClient, ConfigurationError, RecognitionSettings

from .test_amivoice_client import HttpFake
from .test_async_client import RecordingTransport


@pytest.mark.parametrize("value", [True, False, None, USE_CLIENT_DEFAULT])
@pytest.mark.parametrize("inherited", [False, True])
def test_submit_sentiment_override_valid_return_wire(value: object, inherited: bool) -> None:
    """未指定の継承、None解除、明示False送信を区別する"""
    # Given: クライアント既定値と通信記録
    transport = RecordingTransport([{"sessionid": "job1"}])
    base = RecognitionSettings(grammar_file_names="-a-general", sentiment_analysis=True if inherited else USE_CLIENT_DEFAULT)
    client = AmiVoiceAsyncClient(api_key="dummy", settings=base, transport=transport)
    assert RecognitionSettings().sentiment_analysis is USE_CLIENT_DEFAULT
    # When: 呼び出し単位で指定する
    client.submit(b"audio", settings=RecognitionSettings(sentiment_analysis=value))
    # Then: boolだけ送信し、元の設定を変更しない
    resolved = (True if inherited else None) if value is USE_CLIENT_DEFAULT else value
    body = transport.calls[0][3]
    if resolved is None:
        assert b"sentimentAnalysis=" not in body
    else:
        assert f"sentimentAnalysis={resolved}".encode() in body
    assert base.sentiment_analysis is (True if inherited else USE_CLIENT_DEFAULT)


@pytest.mark.parametrize("operation", ["init", "submit"])
@pytest.mark.parametrize("value", [0, 1, "True", "False", 1.5, [], {}])
def test_client_sentiment_type_invalid_raise_before_audio(operation: str, value: object) -> None:
    """エンジン未指定でも型を検証し音声読込と通信を行わない"""
    # Given: 不正な設定
    transport = RecordingTransport([])
    settings = RecognitionSettings(sentiment_analysis=value)
    # When / Then: 設定を先に拒否する
    with pytest.raises(ConfigurationError, match=r"sentiment_analysis.*bool or None"):
        if operation == "init":
            AmiVoiceAsyncClient(api_key="dummy", settings=settings, transport=transport)
        else:
            client = AmiVoiceAsyncClient(
                api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general"), transport=transport
            )
            client.submit("does-not-exist.wav", settings=settings)
    assert not transport.calls


@pytest.mark.parametrize("operation", ["init", "transcribe", "stream"])
@pytest.mark.parametrize("value", [True, False])
def test_sync_sentiment_option_invalid_raise_async_guidance(operation: str, value: bool) -> None:
    """同期HTTPとWebSocketではFalseも含め明示指定を拒否する"""
    # Given: 非同期専用設定
    settings = RecognitionSettings(sentiment_analysis=value)
    # When / Then: 音声や通信の前に代替クライアントを案内する
    with pytest.raises(ConfigurationError, match=r"sentiment_analysis.*AmiVoiceAsyncClient"):
        if operation == "init":
            AmiVoiceClient(api_key="dummy", settings=settings)
        else:
            client = AmiVoiceClient(api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general"))
            if operation == "transcribe":
                client.transcribe("does-not-exist.wav", settings=settings)
            else:
                client.stream(settings=settings)


@pytest.mark.parametrize("value", [None, USE_CLIENT_DEFAULT])
def test_sync_sentiment_unset_valid_return_result(value: object) -> None:
    """同期クライアントの未指定・解除は従来どおり動作する"""
    # Given: 感情設定を送信しない同期クライアント
    transport = HttpFake()
    settings = RecognitionSettings(grammar_file_names="-a-general", sentiment_analysis=value)
    client = AmiVoiceClient(api_key="dummy", settings=settings, hrp_transport=transport)
    # When: HTTP認識とWebSocketセッション作成を行う
    result = client.transcribe(b"audio", settings=RecognitionSettings(sentiment_analysis=value))
    manager = client.stream(settings=RecognitionSettings(sentiment_analysis=value))
    # Then: 認識を維持し非同期パラメータを漏らさない
    assert result.text == "hello" and manager is not None
    assert b"sentimentAnalysis" not in transport.calls[0][2]


def test_submit_sentiment_combined_valid_return_wire_without_new_arguments() -> None:
    """話者・同期互換形式と併用できメソッド引数を増やさない"""
    # Given: 併用設定
    transport = RecordingTransport([{"sessionid": "job1"}])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    # When: すべて有効化して登録する
    client.submit(
        b"audio",
        settings=RecognitionSettings(
            grammar_file_names="-a-general", sentiment_analysis=True, speaker_diarization=True, compatible_with_sync=True
        ),
    )
    # Then: 同一のdに正しい大小文字で送信する
    body = transport.calls[0][3]
    for field in ("sentimentAnalysis", "speakerDiarization", "compatibleWithSync"):
        assert f"{field}=True".encode() in body
    assert "sentiment_analysis" not in inspect.signature(AmiVoiceAsyncClient.submit).parameters
    assert "sentiment_analysis" not in inspect.signature(AmiVoiceAsyncClient).parameters
