"""公式記載例と独立した許可リストで送信形式を照合する"""

import re
from urllib.parse import unquote

import pytest

from amivoice import Codec
from amivoice._params import RecognitionParams
from amivoice._request_parameters import REQUEST_PARAMETERS, build_http_multipart, build_start_command

from .recognition_mock_servers import parse_recognition_multipart as _multipart_parts

# 実装の変換表から期待値を生成せず、公式のrequest-parametersを転記する
# https://docs.amivoice.com/amivoice-api/manual/request-parameters
OFFICIAL_PARAMETER_SCOPES = {
    "authorization": "ws",
    "grammarFileNames": "http",
    "profileId": "both",
    "profileWords": "both",
    "keepFillerToken": "both",
    "segmenterProperties": "both",
    "extension": "both",
    "maxDecodingTime": "both",
    "maxResponseTime": "both",
    "maxDecodingRate": "both",
    "targetResponseTime": "both",
    "targetDecodingRate": "both",
    "recognitionTimeout": "both",
    "confidenceLevel": "both",
    "completeTimeout": "both",
    "wildcardModelPenalty": "both",
    "audioFilterProperties": "http",
    "resultUpdatedInterval": "ws",
    "noInputTimeout": "ws",
}


@pytest.mark.parametrize("api_key", [None, "dummy"])
def test_build_http_multipart_curl_profile_example_valid_return_equivalent_fields(api_key: str | None) -> None:
    """curl例のプロファイル指定を復元でき、音声が最後になる"""
    # Given: https://docs.amivoice.com/amivoice-api/manual/sync-http-interface のcurl設定例
    params = RecognitionParams(grammar_file_names="-a-general", profile_id=":user01")
    audio = b"\x00\xff\r\nnot-a-boundary"
    # When: 本文をMIMEとして読み取る
    request = build_http_multipart(params, audio, api_key=api_key, boundary="official-example")
    parts = _multipart_parts(request.content_type, request.body)
    # Then: URLエンコードを復元すると公式例と一致し、音声を改変しない
    assert [name for name, _ in parts] == (["u", "d", "a"] if api_key else ["d", "a"])
    assert unquote(dict(parts)["d"].decode()) == "grammarFileNames=-a-general profileId=:user01"
    assert parts[-1] == ("a", audio)


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"profile_words": "AMI あみ|AmiVoice あみぼいす"}, 's MSB16K -a-general profileWords="AMI あみ|AmiVoice あみぼいす"'),
        ({"profile_id": ":test"}, "s MSB16K -a-general profileId=:test"),
    ],
)
def test_build_start_command_documented_example_valid_return_exact_header_auth_command(
    kwargs: dict[str, str], expected: str
) -> None:
    """公式のsコマンド設定例をヘッダ認証で送る形式と照合する"""
    # Given: https://docs.amivoice.com/amivoice-api/reference/websocket/command/s-command-packet の2つの設定例
    params = RecognitionParams(grammar_file_names="-a-general", codec="MSB16K", **kwargs)
    # When: 認証ヘッダを使う開始コマンドを生成する
    command = build_start_command(params)
    # Then: 公式例のauthorization部分以外が一致する
    assert command == expected
    assert "authorization=" not in command


def test_build_start_command_extension_quotes_valid_return_doubled_quotes() -> None:
    """JSON内部の引用符を二重化し、%20やバックスラッシュに変換しない"""
    # Given: 公式billing-key形式のJSON
    params = RecognitionParams(grammar_file_names="-a-general", codec="16K", extension='{"client_info":{"billing_key":"tag"}}')
    # When: 開始コマンドを生成する
    command = build_start_command(params)
    # Then: sコマンドの引用符規則に従う
    assert command == 's 16K -a-general extension="{""client_info"":{""billing_key"":""tag""}}"'


def test_request_parameters_official_allowlist_valid_return_exact_scopes() -> None:
    """未掲載キーの追加やHTTPとWebSocketの対応関係の変更を検出する"""
    # Given: 実装とは独立して転記した公式の19キー
    # When: 実装の変換表から送信先キーと対応範囲を取得する
    scopes = {key: scope for key, scope in REQUEST_PARAMETERS.values()}
    # Then: 欠落、余分なキー、対応インタフェースの違いがない
    assert scopes == OFFICIAL_PARAMETER_SCOPES
    assert len(REQUEST_PARAMETERS) == len(scopes)


@pytest.mark.parametrize("interface", ["http", "ws"])
def test_request_builder_all_official_settings_valid_return_only_allowed_keys(interface: str) -> None:
    """全設定を組み合わせても、対象インタフェース以外のキーを生成しない"""
    # Given: ルール専用パラメータを含む全設定、実APIへの送信は行わない
    params = RecognitionParams(
        grammar_file_names="-a-rule-input-private",
        codec="LSB16K",
        profile_id=":test",
        profile_words="AMI あみ",
        keep_filler_token=False,
        segmenter_properties="useDiarizer=1 useLid=ja",
        extension='{"client_info":{"billing_key":"tag"}}',
        max_decoding_time=0,
        max_response_time=1000,
        max_decoding_rate=-1.0,
        target_response_time=0,
        target_decoding_rate=0.5,
        recognition_timeout=1,
        confidence_level=1.0,
        complete_timeout=100,
        wildcard_model_penalty=2.5,
        result_updated_interval=0,
        no_input_timeout=200,
        audio_filter_properties="selectedChannel=0-1" if interface == "http" else None,
    )
    # When: 各インタフェースの送信形式を解析する
    if interface == "http":
        request = build_http_multipart(params, b"audio", boundary="allowlist")
        parts = _multipart_parts(request.content_type, request.body)
        keys = {entry.partition("=")[0] for entry in dict(parts)["d"].decode().split(" ")}
        assert [name for name, _ in parts] == ["d", "c", "a"]
    else:
        command = build_start_command(params, api_key="dummy")
        # 値内のJSONやsegmenterPropertiesではなく、ブロック先頭だけを取得する
        blocks = re.findall(r'(?:[^ "\s]+|"(?:[^"]|"")*")+', command)
        keys = {block.partition("=")[0] for block in blocks[3:]}
    # Then: 0、False、負の無効化値を欠落させず、許可リストの全キーだけを含む
    assert keys == {key for key, scope in OFFICIAL_PARAMETER_SCOPES.items() if scope in ("both", interface)}


@pytest.mark.parametrize("codec", list(Codec))
def test_request_builder_codec_enumeration_valid_return_exact_format(codec: Codec) -> None:
    """全18列挙値でsコマンドとHTTPのcパートの位置を守る"""
    # Given: 公式音声形式の列挙値
    params = RecognitionParams(grammar_file_names="-a-general", codec=codec)
    # When: 同じ設定から両インタフェースを生成する
    command = build_start_command(params)
    request = build_http_multipart(params, b"audio", boundary="codec-example")
    parts = dict(_multipart_parts(request.content_type, request.body))
    # Then: ヘッダ付き形式だけHTTPのcが不要であり、WebSocketは必ず形式を指定する
    assert command == f"s {codec.value} -a-general"
    if codec in (Codec.HEADER_8K, Codec.HEADER_16K):
        assert "c" not in parts
    else:
        assert parts["c"] == codec.value.encode()
