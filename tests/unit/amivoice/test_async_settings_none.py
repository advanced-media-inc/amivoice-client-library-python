"""ベース更新後も非同期クライアントの設定省略契約を維持する"""

import pytest

from amivoice import AmiVoiceAsyncClient, ConfigurationError, RecognitionSettings

from .test_async_client import RecordingTransport, queued


@pytest.mark.parametrize("kwargs", [{}, {"settings": None}, {"settings": RecognitionSettings()}])
def test_init_settings_empty_valid_return_client(kwargs: dict[str, object]) -> None:
    """初期化の省略・None・空設定は保存済みジョブの取得に使える"""
    # Given: エンジン不要のGET応答
    transport = RecordingTransport([queued()])
    # When: 空の認識設定で初期化して取得する
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport, **kwargs)
    snapshot = client.get_job("job1")
    # Then: 初期化を拒否せず本文なしのGETだけ行う
    assert snapshot.status == "queued"
    assert transport.calls[0][0] == "GET" and transport.calls[0][3] is None


def test_submit_settings_none_invalid_raise_before_audio() -> None:
    """呼び出し単位のsettings=Noneは同期と同じく拒否する"""
    # Given: 有効なクライアント既定値
    transport = RecordingTransport([])
    client = AmiVoiceAsyncClient(
        api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general"), transport=transport
    )
    # When / Then: Noneを全解除と解釈せず通信前に拒否する
    with pytest.raises(ConfigurationError, match="settings must be"):
        client.submit("does-not-exist.wav", settings=None)
    assert not transport.calls
