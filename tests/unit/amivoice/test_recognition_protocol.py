"""通信に依存しない HRP / WRP 電文のテスト"""

from email.parser import BytesParser
from urllib.parse import unquote

import pytest

from amivoice._params import RecognitionParams
from amivoice._recognition_protocol import build_hrp_request, build_wrp_start_command, parse_wrp_message
from amivoice.exceptions import RecognitionError


@pytest.mark.parametrize(
    ("field", "wire_name", "value", "expected"),
    [
        ("grammar_file_names", "grammarFileNames", "-a-general", "-a-general"),
        ("profile_id", "profileId", ":profile", ":profile"),
        ("profile_words", "profileWords", '日本語 word "quoted"', '日本語 word "quoted"'),
        ("segmenter_properties", "segmenterProperties", "useDiarizer=1", "useDiarizer=1"),
        ("keep_filler_token", "keepFillerToken", False, "false"),
        ("result_updated_interval", "resultUpdatedInterval", 0, "0"),
        ("complete_timeout", "completeTimeout", 0, "0"),
        ("wildcard_model_penalty", "wildcardModelPenalty", 4.0, "4.0"),
        ("confidence_level", "confidenceLevel", 0.0, "0.0"),
        ("max_decoding_time", "maxDecodingTime", 1000, "1000"),
        ("max_response_time", "maxResponseTime", 2000, "2000"),
        ("max_decoding_rate", "maxDecodingRate", 1.25, "1.25"),
        ("target_response_time", "targetResponseTime", 3000, "3000"),
        ("target_decoding_rate", "targetDecodingRate", -1.0, "-1.0"),
        ("recognition_timeout", "recognitionTimeout", 0, "0"),
    ],
)
def test_build_hrp_request_parameter_valid_return_domain_value(field: str, wire_name: str, value: object, expected: str) -> None:
    """値を欠損なく d パラメータへ変換する"""
    # Given: 直接渡す認識設定
    params = RecognitionParams(**{field: value})
    # When: HTTP 電文を生成する
    request = build_hrp_request(params, "key", b"audio", boundary="test-boundary")
    # Then: URL エンコードした値が multipart 内に含まれる
    assert f"{wire_name}={expected}" in unquote(request.body.decode())


def test_build_hrp_request_multipart_valid_return_audio_and_fields() -> None:
    """音声、認証、コーデック、結果形式を multipart へ変換する"""
    # Given: 任意のバイナリ音声と専用パラメータ
    audio = bytes(range(256))
    params = RecognitionParams(codec="LSB16K", result_type="json", result_encoding="UTF-8", voice_detection="")
    # When: MIME パーサーで生成電文を読み取る
    request = build_hrp_request(params, "secret", audio)
    mime = BytesParser().parsebytes(f"Content-Type: {request.headers['Content-Type']}\r\n\r\n".encode() + request.body)
    parts = {part.get_param("name", header="content-disposition"): part.get_payload(decode=True) for part in mime.get_payload()}
    # Then: バイト列と値が保持される
    assert parts == {"a": audio, "c": b"LSB16K", "r": b"json", "e": b"UTF-8", "u": b"secret", "v": b""}


def test_build_hrp_request_domain_id_valid_return_only_additional_fields() -> None:
    """明示 domain_id では信頼度と音声フィルタだけを追加する"""
    # Given: 独自 domain_id と無視される共通設定
    params = RecognitionParams(
        domain_id="custom=1",
        grammar_file_names="ignored",
        confidence_level=0.3,
        audio_filter_properties="selectedChannel=0-1",
        complete_timeout=100,
    )
    # When: HTTP 電文を生成する
    request = build_hrp_request(params, "key", b"")
    # Then: 既存 domain_id の特例を維持する
    body = unquote(request.body.decode())
    assert "custom=1 confidenceLevel=0.3 audioFilterProperties=selectedChannel=0-1" in body
    assert "grammarFileNames" not in body
    assert "completeTimeout" not in body


def test_build_wrp_start_command_defaults_valid_return_command() -> None:
    """WRP のコーデックとエンジン既定値を維持する"""
    # Given / When: 未指定の認識設定
    command = build_wrp_start_command(RecognitionParams(), "key")
    # Then: デフォルト値を送信する
    assert command == "s 16K \x01 authorization=key"


def test_build_wrp_start_command_quoting_valid_return_escaped_values() -> None:
    """複数グラマ、引用符、日本語、billing_key を電文へ変換する"""
    # Given: 区切りと引用符を含む値
    params = RecognitionParams(
        grammar_file_names="first\x01second",
        profile_words='語 "よみ"',
        billing_key="user01",
        keep_filler_token=False,
        no_input_timeout=0,
    )
    # When: 開始コマンドを生成する
    command = build_wrp_start_command(params, "key")
    # Then: グラマ終端と二重引用符によるエスケープを維持する
    assert command.startswith("s 16K first\x01second\x01 ")
    assert 'profileWords="語 ""よみ"""' in command
    assert 'extension="{""client_info"":{""billing_key"":""user01""}}"' in command
    assert "keepFillerToken=false" in command
    assert "noInputTimeout=0" in command


@pytest.mark.parametrize(
    ("message", "event_type"),
    [
        ("S 10", "utterance_started"),
        ("E 20", "utterance_ended"),
        ("U 途中", "partial"),
        ('A {"text":"確定"}', "final"),
        ('R {"code":"E1"}', "final"),
        ("Q notice", "notification"),
        ("G grammar", "notification"),
    ],
)
def test_parse_wrp_message_event_valid_return_stream_event(message: str, event_type: str) -> None:
    """WRP 応答を公開イベントへ変換する"""
    # Given / When: サーバー応答
    parsed = parse_wrp_message(message)
    # Then: 対応するイベント種別を返す
    assert parsed.event is not None
    assert parsed.event.type == event_type
    if message.startswith("R"):
        assert parsed.event.result.is_error


@pytest.mark.parametrize("message", ["s", "p", "e", "C", ""])
def test_parse_wrp_message_control_valid_return_no_event(message: str) -> None:
    """確認応答と結果作成はユーザーイベントを発行しない"""
    # Given / When: 制御メッセージ
    parsed = parse_wrp_message(message)
    # Then: 制御情報のみ返す
    assert parsed.command == message
    assert parsed.event is None


@pytest.mark.parametrize("message", ["s failed", "p failed", "e failed", "S bad", "E", "A []", "A broken", "X unknown"])
def test_parse_wrp_message_malformed_invalid_raise_RecognitionError(message: str) -> None:
    """サーバーのエラーと不正な電文は例外で伝播する"""
    # Given / When / Then: 不正な応答
    with pytest.raises(RecognitionError):
        parse_wrp_message(message)
