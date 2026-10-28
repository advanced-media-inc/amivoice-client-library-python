"""公式の送信パラメータ生成を確認するテスト"""

from urllib.parse import unquote

import pytest

from amivoice._params import RecognitionParams
from amivoice._request_parameters import build_http_multipart, build_start_command
from amivoice.exceptions import ConfigurationError


def test_build_http_multipart_official_fields_valid_return_audio_last() -> None:
    """公式のパート名だけを生成し音声を最後に配置する"""
    # Given: 辞書とチャネル指定を含む同期HTTP設定
    params = RecognitionParams(
        grammar_file_names="-a-general", codec="LSB16K", profile_words="AMI あみ", audio_filter_properties="selectedChannel=1"
    )
    # When: 決定的なboundaryで本文を生成する
    request = build_http_multipart(params, b"audio-data", api_key="dummy", boundary="test-boundary")
    # Then: 音声が最後であり空白は%20になる
    assert request.body.count(b"Content-Disposition: form-data; name=") == 4
    assert b"profileWords=AMI%20%E3%81%82%E3%81%BF" in request.body
    assert b"audioFilterProperties=selectedChannel%3D1" in request.body
    assert request.body.endswith(b"audio-data\r\n--test-boundary--\r\n")
    assert b'name="r"' not in request.body


def test_build_start_command_quotes_valid_return_official_syntax() -> None:
    """引用符を二重化し公式のsコマンド例と一致させる"""
    # Given: 公式の単語登録例と使用量タグ
    params = RecognitionParams(
        grammar_file_names="-a-general",
        codec="MSB16K",
        profile_words="AMI あみ|AmiVoice あみぼいす",
        extension='{"client_info":{"billing_key":"tag"}}',
    )
    # When: コマンドを生成する
    command = build_start_command(params, api_key="dummy")
    # Then: ダブルクォートで囲み内部の引用符を二重化する
    assert 'profileWords="AMI あみ|AmiVoice あみぼいす"' in command
    assert 'extension="{""client_info"":{""billing_key"":""tag""}}"' in command
    assert command.startswith("s MSB16K -a-general ")
    assert "authorization=dummy" in command
    assert "resultType=" not in command


def test_build_http_multipart_websocket_settings_valid_omit_parameters() -> None:
    """WebSocket専用設定を同期HTTPに送らない"""
    # Given: 共通クライアントにWebSocket専用設定がある
    params = RecognitionParams(grammar_file_names="-a-general", result_updated_interval=1000, no_input_timeout=100)
    # When: HTTPリクエストを生成する
    request = build_http_multipart(params, b"audio")
    # Then: WebSocket専用キーは生成されない
    assert b"resultUpdatedInterval" not in request.body
    assert b"noInputTimeout" not in request.body


@pytest.mark.parametrize(
    "kwargs",
    [
        {"segmenter_properties": "unknown=1"},
        {"audio_filter_properties": "unknown=1"},
        {"audio_filter_properties": "selectedChannel=1-2"},
    ],
)
def test_build_http_multipart_unknown_property_invalid_raise_ConfigurationError(kwargs: dict[str, str]) -> None:
    """未掲載のプロパティを送信前に拒否する"""
    # Given: 公式に記載されていない設定
    params = RecognitionParams(grammar_file_names="-a-general", **kwargs)
    # When / Then: 送信データの生成を拒否する
    with pytest.raises(ConfigurationError):
        build_http_multipart(params, b"audio")


def test_build_http_multipart_grammar_valid_return_encoded_url() -> None:
    """ルールグラマのURLをUTF-8でエンコードする"""
    # Given: 公式ルールグラマ形式
    value = "-a-rule-input-private|https://example.test/sample.gram"
    # When: 本文を生成する
    request = build_http_multipart(RecognitionParams(grammar_file_names=value), b"audio")
    # Then: URLと区切りを正確に復元できる
    assert value in unquote(request.body.decode())
    assert b"%7Chttps%3A%2F%2F" in request.body


@pytest.mark.parametrize("builder", [build_start_command, lambda p: build_http_multipart(p, b"audio")])
def test_request_builder_rule_parameters_invalid_raise_ConfigurationError(builder: object) -> None:
    """ルール専用パラメータを別エンジンで拒否する"""
    # Given: 汎用エンジンにルール専用設定
    params = RecognitionParams(grammar_file_names="-a-general", codec="16K", complete_timeout=1000)
    # When / Then: 送信を拒否する
    with pytest.raises(ConfigurationError, match="rule"):
        builder(params)


@pytest.mark.parametrize("builder", [build_start_command, lambda p: build_http_multipart(p, b"audio")])
def test_request_builder_empty_engine_invalid_raise_ConfigurationError(builder: object) -> None:
    """エンジン名が空のリクエストを送信前に拒否する"""
    # Given: grammar_file_namesの先頭が区切り文字の設定
    params = RecognitionParams(grammar_file_names="|https://example.test/grammar", codec="16K")
    # When / Then: HTTPとWebSocketの両方で送信データの生成を拒否する
    with pytest.raises(ConfigurationError, match="engine"):
        builder(params)
