# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false, reportUnusedCallResult=false

"""AmiVoiceClient のユニットテスト。"""

import threading
from collections.abc import Sequence
from unittest.mock import MagicMock, patch

import pytest

from amivoice import Codec, Engine, ProfileWord
from amivoice._segmenter import SegmenterProperties
from amivoice._stream import StreamConnectionManager, StreamSession
from amivoice.client import (
    _DEFAULT_HRP_URL,
    _DEFAULT_WRP_URL,
    AmiVoiceClient,
)
from amivoice.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ConnectionFailedError,
    RecognitionError,
)
from amivoice.models import RecognitionResult

from ._recognition_fakes import (
    assert_wrp_parameter,
    assert_wrp_parameter_absent,
    http_wire_values,
    make_http_transport,
    make_websocket_transport,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_AmiVoiceClient_construction_stores_api_key() -> None:
    """コンストラクタで api_key が正しく保存されることを確認する。"""
    # Given / When
    client = AmiVoiceClient(api_key="my-key")

    # Then
    assert client._api_key == "my-key"


def test_AmiVoiceClient_construction_uses_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """api_key が省略されたとき環境変数 AMIVOICE_API_KEY が使われることを確認する。"""
    # Given
    monkeypatch.setenv("AMIVOICE_API_KEY", "env-key")

    # When
    client = AmiVoiceClient()

    # Then
    assert client._api_key == "env-key"


def test_AmiVoiceClient_construction_raises_authentication_error_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """api_key も環境変数も未設定のとき AuthenticationError が送出されることを確認する。"""
    # Given
    monkeypatch.delenv("AMIVOICE_API_KEY", raising=False)

    # When / Then
    with pytest.raises(AuthenticationError):
        AmiVoiceClient()


def test_AmiVoiceClient_construction_segmenter_and_raw_properties_invalid_raise_ConfigurationError() -> None:
    """Segmenter と segmenter_properties を同時指定すると ConfigurationError が送出されることを確認する。"""
    # Given: 型付き設定と既存の生文字列設定
    properties = SegmenterProperties(threshold=5000)

    # When / Then: 両方を指定してクライアントを生成すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="segmenter and segmenter_properties"):
        AmiVoiceClient(api_key="key", segmenter=properties, segmenter_properties="threshold=1000")


# ---------------------------------------------------------------------------
# transcribe() — HRP 経路
# ---------------------------------------------------------------------------


def test_AmiVoiceClient_transcribe_success_returns_result() -> None:
    """Transcribe が正常終了したとき RecognitionResult が返ることを確認する。"""
    # Given
    mock_hrp = make_http_transport('{"text": "hello world"}')
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When
    result = client.transcribe(b"audio-data")

    # Then
    assert result == RecognitionResult(raw='{"text": "hello world"}', data={"text": "hello world"})


def test_AmiVoiceClient_transcribe_injected_transport_valid_call_direct_boundary() -> None:
    """注入された HTTP 認識境界を直接一回呼び出すことを確認する。"""
    # Given: テスト注入パスでは connect/disconnect 不要
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When
    client.transcribe(b"audio-data")

    # Then: transport injection 経路では connect/disconnect を呼ばない
    mock_hrp.transcribe.assert_called_once()


def test_AmiVoiceClient_transcribe_uses_default_hrp_url() -> None:
    """api_url を省略したとき _DEFAULT_HRP_URL が HTTP境界 に渡されることを確認する。"""
    # Given
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key")

    # When
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp):
        client.transcribe(b"audio-data")

    # Then
    assert mock_hrp.transcribe.call_args.args[0] == _DEFAULT_HRP_URL


def test_AmiVoiceClient_transcribe_uses_custom_api_url() -> None:
    """transcribe(api_url=...) でカスタム URL が使われることを確認する。"""
    # Given
    mock_hrp = make_http_transport()
    custom = "https://custom.example.com/recognize"
    client = AmiVoiceClient(api_key="key")

    # When
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp):
        client.transcribe(b"audio-data", api_url=custom)

    # Then
    assert mock_hrp.transcribe.call_args.args[0] == custom


def test_AmiVoiceClient_transcribe_uses_constructor_http_api_url() -> None:
    """コンストラクタで http_api_url を指定したとき transcribe がそれを使うことを確認する。"""
    # Given: http_api_url をコンストラクタで指定したクライアント
    mock_hrp = make_http_transport()
    custom = "https://constructor.example.com/recognize"
    client = AmiVoiceClient(api_key="key", http_api_url=custom)

    # When: api_url を省略して transcribe する
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp):
        client.transcribe(b"audio-data")

    # Then: コンストラクタの http_api_url が使われる
    assert mock_hrp.transcribe.call_args.args[0] == custom


@pytest.mark.parametrize("parameter_name", ["http_api_url", "ws_api_url"])
def test_AmiVoiceClient_endpoint_url_none_invalid_raise_ConfigurationError(parameter_name: str) -> None:
    """コンストラクタのエンドポイントURLにNoneを渡すとConfigurationErrorになることを確認する。"""
    # When / Then: Noneを既定URLへ置き換えずConfigurationErrorになる
    with pytest.raises(ConfigurationError, match=f"Invalid {parameter_name}"):
        AmiVoiceClient(api_key="key", **{parameter_name: None})  # pyright: ignore[reportArgumentType]


def test_AmiVoiceClient_transcribe_api_url_none_invalid_raise_ConfigurationError() -> None:
    """transcribeのapi_urlにNoneを渡すと送信前にConfigurationErrorになることを確認する。"""
    # Given: HRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When / Then: Noneを既定URLへ置き換えずConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="Invalid api_url"):
        client.transcribe(b"audio-data", api_url=None)  # pyright: ignore[reportArgumentType]
    mock_hrp.transcribe.assert_not_called()


def test_AmiVoiceClient_transcribe_logging_opt_out_constructor_valid_uses_nolog_url() -> None:
    """コンストラクタのlogging_opt_outで既定HRP URLがnolog URLへ切り替わることを確認する。"""
    # Given: ログ保存なしを指定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, logging_opt_out=True)

    # When: HTTP認識を実行する
    client.transcribe(b"audio-data")

    # Then: nologエンドポイントがHRPへ渡る
    assert mock_hrp.transcribe.call_args.args[0] == "https://acp-api.amivoice.com/v1/nolog/recognize"


@pytest.mark.parametrize(
    "custom_url",
    [
        "https://acp-api-private.amivoice.com/v1/recognize",
        "https://acp-api.amivoice.com/v1/recognize",
    ],
)
def test_AmiVoiceClient_logging_opt_out_logged_http_api_url_invalid_raise_ConfigurationError(custom_url: str) -> None:
    """ログ保存ありのカスタムHRP URLとlogging_opt_outの併用でConfigurationErrorになることを確認する。"""
    # When / Then: ログ保存ありのパスとログ保存なしを同時に指定するとConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="/v1/nolog/recognize"):
        AmiVoiceClient(api_key="key", http_api_url=custom_url, logging_opt_out=True)


def test_AmiVoiceClient_transcribe_logging_opt_out_nolog_custom_url_valid_keeps_custom_url() -> None:
    """ログ保存なしのパスを持つカスタムHRP URLをそのまま使うことを確認する。"""
    # Given: PrivateLinkのログ保存なしURLとログ保存なしを指定したクライアント
    custom = "https://acp-api-private.amivoice.com/v1/nolog/recognize"
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, http_api_url=custom, logging_opt_out=True)

    # When: HTTP認識を実行する
    client.transcribe(b"audio-data")

    # Then: カスタムURLがそのままHRPへ渡る
    assert mock_hrp.transcribe.call_args.args[0] == custom


def test_AmiVoiceClient_transcribe_logging_opt_out_override_logged_custom_url_invalid_raise_ConfigurationError() -> None:
    """呼び出し時にログ保存ありのカスタムURLとlogging_opt_outを併用するとエラーになることを確認する。"""
    # Given: ログ保存ありのカスタムURLを設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        hrp_transport=mock_hrp,
        http_api_url="https://acp-api-private.amivoice.com/v1/recognize",
    )

    # When / Then: 呼び出し時にログ保存なしを指定するとConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="/v1/nolog/recognize"):
        client.transcribe(b"audio-data", logging_opt_out=True)
    with pytest.raises(ConfigurationError, match="/v1/nolog/recognize"):
        client.transcribe(
            b"audio-data",
            api_url="https://acp-api.amivoice.com/v1/recognize",
            logging_opt_out=True,
        )
    mock_hrp.transcribe.assert_not_called()


def test_AmiVoiceClient_transcribe_logging_opt_out_override_nolog_custom_url_valid_uses_custom_url() -> None:
    """呼び出し時のログ保存なしカスタムURLとlogging_opt_outを併用できることを確認する。"""
    # Given: ログ保存なしを指定したHRPクライアント
    custom = "https://acp-api-private.amivoice.com/v1/nolog/recognize"
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, logging_opt_out=True)

    # When: ログ保存なしのカスタムURLを指定してHTTP認識を実行する
    client.transcribe(b"audio-data", api_url=custom)

    # Then: カスタムURLがそのままHRPへ渡る
    assert mock_hrp.transcribe.call_args.args[0] == custom


@pytest.mark.parametrize(
    ("constructor_value", "override_value", "expected_url"),
    [
        (False, True, "https://acp-api.amivoice.com/v1/nolog/recognize"),
        (True, False, "https://acp-api.amivoice.com/v1/recognize"),
    ],
)
def test_AmiVoiceClient_transcribe_logging_opt_out_override_valid_uses_expected_url(
    constructor_value: bool,
    override_value: bool,
    expected_url: str,
) -> None:
    """transcribeのlogging_opt_out overrideがコンストラクタ設定を上書きすることを確認する。"""
    # Given: logging_opt_outの既定値を設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, logging_opt_out=constructor_value)

    # When: 呼び出し時にlogging_opt_outを上書きしてHTTP認識を実行する
    client.transcribe(b"audio-data", logging_opt_out=override_value)

    # Then: overrideに対応するエンドポイントがHRPへ渡る
    assert mock_hrp.transcribe.call_args.args[0] == expected_url


def test_AmiVoiceClient_stream_api_url_none_invalid_raise_ConfigurationError() -> None:
    """streamのapi_urlにNoneを渡すと接続前にConfigurationErrorになることを確認する。"""
    # Given: WebSocketクライアント
    client = AmiVoiceClient(api_key="key")

    # When / Then: Noneを既定URLへ置き換えずConfigurationErrorになる
    with (
        patch("amivoice._stream._connect_websocket_transport") as mock_build,
        pytest.raises(ConfigurationError, match="Invalid api_url"),
    ):
        client.stream(api_url=None)  # pyright: ignore[reportArgumentType]
    mock_build.assert_not_called()


def test_AmiVoiceClient_stream_logging_opt_out_constructor_valid_uses_nolog_url() -> None:
    """コンストラクタのlogging_opt_outで既定WRP URLがnolog URLへ切り替わることを確認する。"""
    # Given: ログ保存なしを指定したWebSocketクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", logging_opt_out=True)

    # When: ストリーミングセッションを開始する
    with patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build, client.stream() as session:
        session.end()

    # Then: nologエンドポイントがWRPへ渡る
    assert mock_build.call_args.args[0] == "wss://acp-api.amivoice.com/v1/nolog/"


@pytest.mark.parametrize(
    "custom_url",
    [
        "wss://acp-api-private.amivoice.com/v1/",
        "wss://acp-api.amivoice.com/v1/",
        "wss://acp-api.amivoice.com/v1/nolog",
    ],
)
def test_AmiVoiceClient_logging_opt_out_logged_ws_api_url_invalid_raise_ConfigurationError(custom_url: str) -> None:
    """ログ保存ありのカスタムWRP URLとlogging_opt_outの併用でConfigurationErrorになることを確認する。"""
    # When / Then: 末尾のスラッシュがないURLを含め、ログ保存ありのパスはConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="/v1/nolog/"):
        AmiVoiceClient(api_key="key", ws_api_url=custom_url, logging_opt_out=True)


def test_AmiVoiceClient_stream_logging_opt_out_nolog_custom_url_valid_keeps_custom_url() -> None:
    """ログ保存なしのパスを持つカスタムWRP URLをそのまま使うことを確認する。"""
    # Given: PrivateLinkのログ保存なしURLとログ保存なしを指定したクライアント
    custom = "wss://acp-api-private.amivoice.com/v1/nolog/"
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", ws_api_url=custom, logging_opt_out=True)

    # When: ストリーミングセッションを開始する
    with patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build, client.stream() as session:
        session.end()

    # Then: カスタムURLがそのままWRPへ渡る
    assert mock_build.call_args.args[0] == custom


def test_AmiVoiceClient_stream_logging_opt_out_override_logged_custom_url_invalid_raise_ConfigurationError() -> None:
    """呼び出し時にログ保存ありのカスタムWRP URLとlogging_opt_outを併用するとエラーになることを確認する。"""
    # Given: ログ保存なしを指定したWebSocketクライアント
    client = AmiVoiceClient(api_key="key", logging_opt_out=True)

    # When / Then: 末尾のスラッシュがないnolog URLを指定するとConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="/v1/nolog/"):
        client.stream(api_url="wss://acp-api.amivoice.com/v1/nolog")


@pytest.mark.parametrize(
    ("constructor_value", "override_value", "expected_url"),
    [
        (False, True, "wss://acp-api.amivoice.com/v1/nolog/"),
        (True, False, "wss://acp-api.amivoice.com/v1/"),
    ],
)
def test_AmiVoiceClient_stream_logging_opt_out_override_valid_uses_expected_url(
    constructor_value: bool,
    override_value: bool,
    expected_url: str,
) -> None:
    """streamのlogging_opt_out overrideがコンストラクタ設定を上書きすることを確認する。"""
    # Given: logging_opt_outの既定値を設定したWebSocketクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", logging_opt_out=constructor_value)

    # When: 呼び出し時にlogging_opt_outを上書きしてストリーミングを開始する
    with (
        patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build,
        client.stream(logging_opt_out=override_value) as session,
    ):
        session.end()

    # Then: overrideに対応するエンドポイントがWRPへ渡る
    assert mock_build.call_args.args[0] == expected_url


@pytest.mark.parametrize("value", [None, "false", 1])
def test_AmiVoiceClient_logging_opt_out_not_bool_invalid_raise_ConfigurationError(value: object) -> None:
    """コンストラクタのlogging_opt_outがboolでない場合にConfigurationErrorになることを確認する。"""
    # When / Then: bool以外を指定するとConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="logging_opt_out"):
        AmiVoiceClient(api_key="key", logging_opt_out=value)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [None, "false", 0])
def test_AmiVoiceClient_transcribe_logging_opt_out_override_not_bool_invalid_raise_ConfigurationError(value: object) -> None:
    """transcribeのlogging_opt_out overrideがboolでない場合に送信前にエラーになることを確認する。"""
    # Given: ログ保存なしを指定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, logging_opt_out=True)

    # When / Then: bool以外のoverrideはFalseとして扱わずConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="logging_opt_out"):
        client.transcribe(b"audio-data", logging_opt_out=value)  # pyright: ignore[reportArgumentType]
    mock_hrp.transcribe.assert_not_called()


@pytest.mark.parametrize("value", [None, "false", 0])
def test_AmiVoiceClient_stream_logging_opt_out_override_not_bool_invalid_raise_ConfigurationError(value: object) -> None:
    """streamのlogging_opt_out overrideがboolでない場合にConfigurationErrorになることを確認する。"""
    # Given: ログ保存なしを指定したWebSocketクライアント
    client = AmiVoiceClient(api_key="key", logging_opt_out=True)

    # When / Then: bool以外のoverrideはFalseとして扱わずConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="logging_opt_out"):
        client.stream(logging_opt_out=value)  # pyright: ignore[reportArgumentType]


def test_AmiVoiceClient_transcribe_recognition_timeout_passed_to_protocol() -> None:
    """recognition_timeout が recognitionTimeout に文字列で渡されることを確認する。"""
    # Given
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, recognition_timeout=30000)

    # When
    client.transcribe(b"audio-data")

    # Then
    assert http_wire_values(mock_hrp)["recognitionTimeout"] == "30000"


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "value", "expected"),
    [
        ("max_decoding_time", "maxDecodingTime", 1000, "1000"),
        ("max_response_time", "maxResponseTime", 2000, "2000"),
        ("max_decoding_rate", "maxDecodingRate", 1.25, "1.25"),
        ("target_response_time", "targetResponseTime", 3000, "3000"),
        ("target_decoding_rate", "targetDecodingRate", -1.0, "-1.0"),
    ],
)
def test_AmiVoiceClient_transcribe_processing_parameter_constructor_default_valid_passes_string(
    parameter_name: str,
    wire_name: str,
    value: int | float,
    expected: str,
) -> None:
    """コンストラクタの処理時間制御パラメータが HRP 電文境界 に文字列で渡ることを確認する"""
    # Given: 処理時間制御パラメータを設定した HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, **{parameter_name: value})

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: 対応する 電文境界 に文字列で値が渡る
    assert http_wire_values(mock_hrp)[wire_name] == expected


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "default_value", "override_value", "expected"),
    [
        ("max_decoding_time", "maxDecodingTime", 1000, 2000, "2000"),
        ("max_response_time", "maxResponseTime", 2000, 3000, "3000"),
        ("max_decoding_rate", "maxDecodingRate", 1.25, 2.5, "2.5"),
        ("target_response_time", "targetResponseTime", 3000, 4000, "4000"),
        ("target_decoding_rate", "targetDecodingRate", -1.0, 0.75, "0.75"),
    ],
)
def test_AmiVoiceClient_transcribe_processing_parameter_call_override_valid_passes_string(
    parameter_name: str,
    wire_name: str,
    default_value: int | float,
    override_value: int | float,
    expected: str,
) -> None:
    """Transcribe の処理時間制御パラメータ override が既定値を上書きすることを確認する"""
    # Given: 処理時間制御パラメータの既定値を設定した HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, **{parameter_name: default_value})

    # When: 呼び出し時に処理時間制御パラメータを上書きして transcribe を実行する
    client.transcribe(b"audio-data", **{parameter_name: override_value})

    # Then: override の値が対応する 電文境界 に文字列で渡る
    assert http_wire_values(mock_hrp)[wire_name] == expected


@pytest.mark.parametrize(
    "wire_name",
    [
        "maxDecodingTime",
        "maxResponseTime",
        "maxDecodingRate",
        "targetResponseTime",
        "targetDecodingRate",
    ],
)
def test_AmiVoiceClient_transcribe_processing_parameter_omitted_valid_not_set(wire_name: str) -> None:
    """処理時間制御パラメータ未指定時に HRP 電文境界 が呼ばれないことを確認する"""
    # Given: 処理時間制御パラメータを指定していない HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: サーバー側のデフォルトに委ねるため 電文境界 は呼ばれない
    assert wire_name not in http_wire_values(mock_hrp)


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "value", "expected"),
    [
        ("max_decoding_time", "maxDecodingTime", 1000, "1000"),
        ("max_response_time", "maxResponseTime", 2000, "2000"),
        ("max_decoding_rate", "maxDecodingRate", 1.25, "1.25"),
        ("target_response_time", "targetResponseTime", 3000, "3000"),
        ("target_decoding_rate", "targetDecodingRate", -1.0, "-1.0"),
    ],
)
def test_AmiVoiceClient_stream_processing_parameter_constructor_default_valid_passes_string(
    parameter_name: str,
    wire_name: str,
    value: int | float,
    expected: str,
) -> None:
    """コンストラクタの処理時間制御パラメータが WRP protocol に文字列で渡ることを確認する"""
    # Given: 処理時間制御パラメータを設定した WebSocket クライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", **{parameter_name: value})

    # When: stream を開く
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream() as session:
        session.end()

    # Then: 対応する protocol に文字列で値が渡る
    assert_wrp_parameter(mock_wrp, wire_name, expected)


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "default_value", "override_value", "expected"),
    [
        ("max_decoding_time", "maxDecodingTime", 1000, 2000, "2000"),
        ("max_response_time", "maxResponseTime", 2000, 3000, "3000"),
        ("max_decoding_rate", "maxDecodingRate", 1.25, 2.5, "2.5"),
        ("target_response_time", "targetResponseTime", 3000, 4000, "4000"),
        ("target_decoding_rate", "targetDecodingRate", -1.0, 0.75, "0.75"),
    ],
)
def test_AmiVoiceClient_stream_processing_parameter_call_override_valid_passes_string(
    parameter_name: str,
    wire_name: str,
    default_value: int | float,
    override_value: int | float,
    expected: str,
) -> None:
    """Stream の処理時間制御パラメータ override が既定値を上書きすることを確認する"""
    # Given: 処理時間制御パラメータの既定値を設定した WebSocket クライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", **{parameter_name: default_value})

    # When: 呼び出し時に処理時間制御パラメータを上書きして stream を開く
    with (
        patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp),
        client.stream(**{parameter_name: override_value}) as session,
    ):
        session.end()

    # Then: override の値が対応する protocol に文字列で渡る
    assert_wrp_parameter(mock_wrp, wire_name, expected)


@pytest.mark.parametrize(
    "wire_name",
    [
        "maxDecodingTime",
        "maxResponseTime",
        "maxDecodingRate",
        "targetResponseTime",
        "targetDecodingRate",
    ],
)
def test_AmiVoiceClient_stream_processing_parameter_omitted_valid_not_set(wire_name: str) -> None:
    """処理時間制御パラメータ未指定時に WRP protocol が呼ばれないことを確認する"""
    # Given: 処理時間制御パラメータを指定していない WebSocket クライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key")

    # When: stream を開く
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream() as session:
        session.end()

    # Then: サーバー側のデフォルトに委ねるため protocol は呼ばれない
    assert_wrp_parameter_absent(mock_wrp, wire_name)


def test_AmiVoiceClient_transcribe_confidence_level_constructor_default_valid_passes_repr() -> None:
    """コンストラクタの confidence_level が repr 文字列で HRP に渡ることを確認する。"""
    # Given: confidence_level を設定した HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, confidence_level=0.3)

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: 小数表記を維持した文字列が 電文境界 に渡される
    assert http_wire_values(mock_hrp)["confidenceLevel"] == "0.3"


def test_AmiVoiceClient_transcribe_confidence_level_call_override_valid_passes_repr() -> None:
    """Transcribe の confidence_level override がインスタンス既定値を上書きすることを確認する。"""
    # Given: confidence_level の既定値を設定した HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, confidence_level=0.3)

    # When: 呼び出し時に confidence_level を上書きして transcribe を実行する
    client.transcribe(b"audio-data", confidence_level=0.7)

    # Then: override の値が repr 文字列で 電文境界 に渡される
    assert http_wire_values(mock_hrp)["confidenceLevel"] == "0.7"


def test_AmiVoiceClient_transcribe_confidence_level_omitted_valid_not_set() -> None:
    """confidence_level 未指定時に HRP の 電文境界 が呼ばれないことを確認する。"""
    # Given: confidence_level を指定していない HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: サーバー側のデフォルトに委ねるため 電文境界 は呼ばれない
    assert "confidenceLevel" not in http_wire_values(mock_hrp)


def test_AmiVoiceClient_transcribe_billing_key_constructor_default_valid_passes_extension() -> None:
    """コンストラクタの billing_key が HRP の extension 電文境界 に渡ることを確認する"""
    # Given: billing_key を設定した HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, billing_key="user01")

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: billing_key 用のコンパクト JSON が extension 電文境界 に渡る
    assert http_wire_values(mock_hrp)["extension"] == '{"client_info":{"billing_key":"user01"}}'


def test_AmiVoiceClient_transcribe_billing_key_call_override_valid_passes_extension() -> None:
    """Transcribe の billing_key override がインスタンス既定値を上書きすることを確認する"""
    # Given: billing_key の既定値を設定した HRP クライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, billing_key="default")

    # When: 呼び出し時に billing_key を上書きして transcribe を実行する
    client.transcribe(b"audio-data", billing_key="override")

    # Then: override の billing_key から生成した JSON が渡る
    assert http_wire_values(mock_hrp)["extension"] == '{"client_info":{"billing_key":"override"}}'


def test_AmiVoiceClient_transcribe_extension_and_billing_key_invalid_raise_ConfigurationError() -> None:
    """Transcribe で extension と billing_key を同時指定すると ConfigurationError が送出されることを確認する"""
    # Given: 既存 extension を設定した HRP クライアント
    client = AmiVoiceClient(api_key="key", extension="legacy-extension")

    # When / Then: 呼び出し時に billing_key を追加すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="extension and billing_key"):
        client.transcribe(b"audio-data", billing_key="user01")


def test_AmiVoiceClient_transcribe_segmenter_valid_passes_generated_parameter() -> None:
    """型付き segmenter 設定が HRP の 電文境界 に渡されることを確認する。"""
    # Given: 型付きセグメンター設定と注入済み HRP トランスポート
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        hrp_transport=mock_hrp,
        segmenter=SegmenterProperties(speaker_diarization=True, diarizer_alpha=1e-20),
    )

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: 生成された segmenterProperties 文字列が 電文境界 に渡される
    assert http_wire_values(mock_hrp)["segmenterProperties"] == "useDiarizer=1 diarizerAlpha=1e-20"


def test_AmiVoiceClient_transcribe_raw_segmenter_properties_valid_passes_unchanged() -> None:
    """既存の生 segmenter_properties 文字列がそのまま HRP に渡ることを確認する。"""
    # Given: 生文字列を指定したクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, segmenter_properties="threshold=5000")

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: 生文字列が変更されず 電文境界 に渡される
    assert http_wire_values(mock_hrp)["segmenterProperties"] == "threshold=5000"


def test_AmiVoiceClient_transcribe_segmenter_and_raw_properties_invalid_raise_ConfigurationError() -> None:
    """Transcribe で segmenter と生文字列を同時指定すると ConfigurationError が送出されることを確認する。"""
    # Given: 認証済みクライアントと型付き設定
    client = AmiVoiceClient(api_key="key")
    properties = SegmenterProperties(threshold=5000)

    # When / Then: 両方を指定して transcribe すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="segmenter and segmenter_properties"):
        client.transcribe(
            b"audio-data",
            segmenter=properties,
            segmenter_properties="threshold=1000",
        )


def test_AmiVoiceClient_transcribe_call_args_override_instance_defaults() -> None:
    """transcribe() の呼び出し時引数が同名のインスタンス既定値を上書きすることを確認する。"""
    # Given: 既定値を保持したクライアントと注入済み HRP トランスポート
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        grammar_file_names="-a-general",
        codec="16K",
        keep_filler_token=True,
        connect_timeout=1000,
        receive_timeout=2000,
        extension="default-tag",
        hrp_transport=mock_hrp,
    )

    # When: 呼び出し時に一部設定を上書きして transcribe する
    client.transcribe(
        b"audio-data",
        grammar_file_names="-a-medical",
        codec="8K",
        keep_filler_token=False,
        connect_timeout=3000,
        receive_timeout=4000,
        extension="override-tag",
    )

    # Then: 呼び出し時引数が 電文境界 に渡される
    assert http_wire_values(mock_hrp)["grammarFileNames"] == "-a-medical"
    assert http_wire_values(mock_hrp)["codec"] == "8K"
    assert http_wire_values(mock_hrp)["keepFillerToken"] == "false"
    assert http_wire_values(mock_hrp)["connectTimeout"] == 3000
    assert http_wire_values(mock_hrp)["receiveTimeout"] == 4000
    assert http_wire_values(mock_hrp)["extension"] == "override-tag"


def test_AmiVoiceClient_transcribe_constant_params_valid_return_wire_values() -> None:
    """CodecとEngineの定数を指定した場合にAPIへ送る文字列が電文境界へ渡されることを確認する。"""
    # Given: 定数で既定値を保持したクライアントと注入済み HRP トランスポート
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        grammar_file_names=Engine.A_GENERAL,
        codec=Codec.HEADER_16K,
        hrp_transport=mock_hrp,
    )

    # When: 呼び出し時にcodecを定数で上書きして transcribe する
    client.transcribe(b"audio-data", codec=Codec.LSB8K)

    # Then: 定数の値が文字列として 電文境界 に渡される
    assert http_wire_values(mock_hrp)["grammarFileNames"] == "-a-general"
    assert http_wire_values(mock_hrp)["codec"] == "LSB8K"


def test_AmiVoiceClient_transcribe_omitted_args_use_instance_defaults() -> None:
    """transcribe() で引数を省略した場合にインスタンス既定値が使われることを確認する。"""
    # Given: 既定値を保持したクライアントと注入済み HRP トランスポート
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        grammar_file_names="-a-general",
        codec="16K",
        keep_filler_token=True,
        connect_timeout=1000,
        receive_timeout=2000,
        extension="default-tag",
        hrp_transport=mock_hrp,
    )

    # When: override を渡さず transcribe する
    client.transcribe(b"audio-data")

    # Then: コンストラクタ既定値が 電文境界 に渡される
    assert http_wire_values(mock_hrp)["grammarFileNames"] == "-a-general"
    assert http_wire_values(mock_hrp)["codec"] == "16K"
    assert http_wire_values(mock_hrp)["keepFillerToken"] == "true"
    assert http_wire_values(mock_hrp)["connectTimeout"] == 1000
    assert http_wire_values(mock_hrp)["receiveTimeout"] == 2000
    assert http_wire_values(mock_hrp)["extension"] == "default-tag"


def test_AmiVoiceClient_transcribe_connect_fails_raises_connection_error() -> None:
    """実 transport で接続失敗のとき ConnectionFailedError が送出されることを確認する。"""
    # Given
    mock_hrp = make_http_transport(connect_ok=False)
    client = AmiVoiceClient(api_key="key")

    # When / Then
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp), pytest.raises(ConnectionFailedError):
        client.transcribe(b"audio-data")


def test_AmiVoiceClient_transcribe_server_error_raises_recognition_error() -> None:
    """サーバーエラーレスポンスのとき RecognitionError が送出されることを確認する。"""
    # Given
    mock_hrp = make_http_transport('\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}')
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When / Then
    with pytest.raises(RecognitionError, match="bad request") as exc_info:
        client.transcribe(b"audio-data")

    assert exc_info.value.result is not None
    assert exc_info.value.result.is_error is True


def test_AmiVoiceClient_transcribe_raise_on_error_false_returns_error_result() -> None:
    """raise_on_error=False のときエラー結果が例外なく返ることを確認する。"""
    # Given
    mock_hrp = make_http_transport('\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}')
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When
    result = client.transcribe(b"audio-data", raise_on_error=False)

    # Then
    assert result.is_error is True
    assert result.data == {"code": "E001", "message": "bad request"}


def test_AmiVoiceClient_transcribe_concurrent_calls_are_independent() -> None:
    """複数スレッドから transcribe を同時呼び出しても独立して動作することを確認する。"""
    # Given: スレッドごとに独立した mock HRP を生成する
    call_count = 0
    lock = threading.Lock()
    results: list[RecognitionResult] = []
    errors: list[Exception] = []

    def make_hrp() -> MagicMock:
        nonlocal call_count
        with lock:
            call_count += 1
        return make_http_transport(f'{{"text": "result-{call_count}"}}')

    def worker() -> None:
        try:
            c = AmiVoiceClient(api_key="key")
            results.append(c.transcribe(b"audio"))
        except Exception as exc:
            errors.append(exc)

    # When: 4 スレッドから同時実行
    # NOTE: patch はスレッド間で共有される属性を差し替えるためスレッドセーフではない。
    # スレッド起動の外側で 1 度だけ patch を張り、スレッドセーフな make_hrp（ロック保護）で
    # 各スレッドに独立したモックを配る。
    with patch("amivoice.client._construct_hrp_transport", side_effect=make_hrp):
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # Then: エラーなし・4件の結果
    assert errors == []
    assert len(results) == 4


# ---------------------------------------------------------------------------
# stream() — WRP 経路
# ---------------------------------------------------------------------------


def test_AmiVoiceClient_stream_returns_stream_connection_manager() -> None:
    """stream() が StreamConnectionManager を返すことを確認する。"""
    # Given: AmiVoiceClient インスタンス
    client = AmiVoiceClient(api_key="key")

    # When: stream() を呼び出す
    manager = client.stream()

    # Then: StreamConnectionManager が返る
    assert isinstance(manager, StreamConnectionManager)


@pytest.mark.parametrize(
    "audio_filter_kwargs",
    [{"selected_channel": 1}, {"audio_filter_properties": "selectedChannel=1"}],
)
def test_AmiVoiceClient_stream_audio_filter_configured_invalid_raise_ConfigurationError(
    audio_filter_kwargs: dict[str, object],
) -> None:
    """コンストラクタの音声フィルタ設定がstream()で黙って捨てられないことを確認する"""
    # Given: チャネル選択を設定したWRPクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp, **audio_filter_kwargs)  # type: ignore[arg-type]

    # When / Then: stream()はWebSocket非対応の設定としてConfigurationErrorを送出する
    with pytest.raises(ConfigurationError, match="not supported by stream"):
        client.stream()
    mock_wrp.connect.assert_not_called()


def test_AmiVoiceClient_stream_context_manager_returns_stream_session() -> None:
    """With client.stream() as session: で StreamSession が返ることを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When / Then: with ブロック内で StreamSession が取得できる
    with client.stream() as session:
        assert isinstance(session, StreamSession)


def test_AmiVoiceClient_stream_write_and_end_sends_audio() -> None:
    """session.write() でデータが バイナリメッセージに渡されることを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: session.write() でチャンクを送信し、end() で終了する
    with client.stream() as session:
        session.write(b"chunk1")
        session.end()

    # Then: バイナリメッセージに正しい引数で呼び出されている
    mock_wrp.send_binary.assert_called_once_with(b"pchunk1")


def test_AmiVoiceClient_stream_poll_yields_events() -> None:
    """session.poll() がストリーミングイベントを yield することを確認する。"""
    # Given: 1件の結果を返すモック WRP トランスポート
    mock_wrp = make_websocket_transport(['{"text": "hello"}'])
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: end() 後に poll() でイベントを収集する
    with client.stream() as session:
        session.end()
        events = list(session.poll())

    # Then: resultFinalized → StreamEvent(is_final=True) が1件
    final_events = [e for e in events if e.is_final]
    assert len(final_events) == 1
    assert final_events[0].text == "hello"
    assert final_events[0].result is not None
    assert final_events[0].result.data["text"] == "hello"


def test_AmiVoiceClient_stream_results_returns_all_finalized() -> None:
    """session.results() が確定済み結果リストを返すことを確認する。"""
    # Given: 2件の結果を返すモック WRP トランスポート
    mock_wrp = make_websocket_transport(['{"text": "part1"}', '{"text": "part2"}'])
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: セッションを実行し poll() でキューを消費してから results() を呼ぶ
    with client.stream() as session:
        session.end()
        _ = list(session.poll())  # キューを消費
    results = session.results()

    # Then: 2件の確定済み結果が順序どおりに返る
    assert len(results) == 2
    assert results[0].data["text"] == "part1"
    assert results[1].data["text"] == "part2"


def test_AmiVoiceClient_stream_disconnect_called_on_exit() -> None:
    """With ブロックを抜けると disconnect が呼ばれることを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: with ブロックを正常終了する
    with client.stream() as session:
        session.end()

    # Then: disconnect が1回呼ばれている（リソースリークなし）
    mock_wrp.close.assert_called_once()


def test_AmiVoiceClient_stream_uses_default_wrp_url() -> None:
    """api_url を省略したとき _DEFAULT_WRP_URL が使われることを確認する。"""
    # Given: wrp_transport を注入しない AmiVoiceClient（実 transport ファクトリをモック）
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key")

    # When: api_url を省略して stream() を開く
    with patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build, client.stream() as session:
        session.end()

    # Then: ファクトリの第1引数（api_url）に _DEFAULT_WRP_URL が渡されている
    _, _kwargs = mock_build.call_args
    # 第1引数は api_url、第2引数は params
    positional = mock_build.call_args.args
    assert positional[0] == _DEFAULT_WRP_URL


def test_AmiVoiceClient_stream_uses_custom_api_url() -> None:
    """stream(api_url=...) でカスタム URL が使われることを確認する。"""
    # Given: カスタム WRP エンドポイント URL
    mock_wrp = make_websocket_transport()
    custom = "wss://custom.example.com/v1/"
    client = AmiVoiceClient(api_key="key")

    # When: カスタム URL を渡して stream() を開く
    with (
        patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build,
        client.stream(api_url=custom) as session,
    ):
        session.end()

    # Then: ファクトリの第1引数にカスタム URL が渡されている
    positional = mock_build.call_args.args
    assert positional[0] == custom


def test_AmiVoiceClient_stream_uses_constructor_ws_api_url() -> None:
    """コンストラクタで ws_api_url を指定したとき stream がそれを使うことを確認する。"""
    # Given: ws_api_url をコンストラクタで指定したクライアント
    mock_wrp = make_websocket_transport()
    custom = "wss://constructor.example.com/v1/"
    client = AmiVoiceClient(api_key="key", ws_api_url=custom)

    # When: api_url を省略して stream() を開く
    with (
        patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build,
        client.stream() as session,
    ):
        session.end()

    # Then: コンストラクタの ws_api_url が第1引数に渡される
    assert mock_build.call_args.args[0] == custom


def test_AmiVoiceClient_stream_segmenter_valid_passes_generated_parameter() -> None:
    """型付き segmenter 設定が WRP の protocol に渡されることを確認する。"""
    # Given: 型付き設定を指定したクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key")
    properties = SegmenterProperties(languages=("ja", "en"))

    # When: 型付き設定で stream を開く
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream(segmenter=properties) as session:
        session.end()

    # Then: 生成された文字列が WRP の protocol に渡される
    assert_wrp_parameter(mock_wrp, "segmenterProperties", "useLid=ja,en")


def test_AmiVoiceClient_stream_confidence_level_call_override_valid_passes_repr() -> None:
    """Stream の confidence_level override が repr 文字列で WRP に渡ることを確認する。"""
    # Given: confidence_level の既定値を設定したクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", confidence_level=0.3)

    # When: 呼び出し時に confidence_level を上書きして stream を開く
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream(confidence_level=0.7) as session:
        session.end()

    # Then: override の値が repr 文字列で protocol に渡される
    assert_wrp_parameter(mock_wrp, "confidenceLevel", "0.7")


def test_AmiVoiceClient_stream_confidence_level_omitted_valid_not_set() -> None:
    """confidence_level 未指定時に WRP の protocol が呼ばれないことを確認する。"""
    # Given: confidence_level を指定していないクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key")

    # When: confidence_level を指定せず stream を開く
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream() as session:
        session.end()

    # Then: サーバー側のデフォルトに委ねるため protocol は呼ばれない
    assert_wrp_parameter_absent(mock_wrp, "confidenceLevel")


def test_AmiVoiceClient_stream_billing_key_constructor_default_valid_passes_extension() -> None:
    """コンストラクタの billing_key が WRP の extension protocol に渡ることを確認する"""
    # Given: billing_key を設定した WebSocket クライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", billing_key="user01")

    # When: billing_key を設定した stream を開く
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream() as session:
        session.end()

    # Then: billing_key 用のコンパクト JSON が extension protocol に渡る
    assert_wrp_parameter(mock_wrp, "extension", '{"client_info":{"billing_key":"user01"}}')


def test_AmiVoiceClient_stream_billing_key_call_override_valid_passes_extension() -> None:
    """Stream の billing_key override がインスタンス既定値を上書きすることを確認する"""
    # Given: billing_key の既定値を設定した WebSocket クライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", billing_key="default")

    # When: 呼び出し時に billing_key を上書きして stream を開く
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream(billing_key="override") as session:
        session.end()

    # Then: override の billing_key から生成した JSON が渡る
    assert_wrp_parameter(mock_wrp, "extension", '{"client_info":{"billing_key":"override"}}')


def test_AmiVoiceClient_stream_extension_and_billing_key_invalid_raise_ConfigurationError() -> None:
    """Stream で extension と billing_key を同時指定すると ConfigurationError が送出されることを確認する"""
    # Given: 既存 extension を設定した WebSocket クライアント
    client = AmiVoiceClient(api_key="key", extension="legacy-extension")

    # When / Then: 呼び出し時に billing_key を追加すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="extension and billing_key"):
        client.stream(billing_key="user01")


def test_AmiVoiceClient_stream_segmenter_and_raw_properties_invalid_raise_ConfigurationError() -> None:
    """Stream で segmenter と生文字列を同時指定すると ConfigurationError が送出されることを確認する。"""
    # Given: 認証済みクライアントと型付き設定
    client = AmiVoiceClient(api_key="key")
    properties = SegmenterProperties(threshold=5000)

    # When / Then: 両方を指定して stream を呼ぶと ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="segmenter and segmenter_properties"):
        client.stream(segmenter=properties, segmenter_properties="threshold=1000")


def test_AmiVoiceClient_stream_call_args_override_instance_defaults() -> None:
    """stream() の呼び出し時引数が同名のインスタンス既定値を上書きすることを確認する。"""
    # Given: 既定値を保持したクライアントとモック WRP
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(
        api_key="key",
        grammar_file_names="-a-general",
        codec="16K",
        keep_filler_token=True,
        connect_timeout=1000,
        receive_timeout=2000,
        extension="default-tag",
        no_input_timeout=5000,
    )

    # When: 呼び出し時に一部設定を上書きして stream() を開く
    with (
        patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build,
        client.stream(
            grammar_file_names="-a-medical",
            codec="8K",
            keep_filler_token=False,
            connect_timeout=3000,
            receive_timeout=4000,
            extension="override-tag",
            no_input_timeout=7000,
        ) as session,
    ):
        session.end()

    # Then: 呼び出し時引数が RecognitionParams として WRP transport builder に渡される
    params = mock_build.call_args.args[1]
    assert params.grammar_file_names == "-a-medical"
    assert params.codec == "8K"
    assert params.keep_filler_token is False
    assert params.connect_timeout == 3000
    assert params.receive_timeout == 4000
    assert params.extension == "override-tag"
    assert params.no_input_timeout == 7000


def test_AmiVoiceClient_stream_omitted_args_use_instance_defaults() -> None:
    """stream() で引数を省略した場合にインスタンス既定値が使われることを確認する。"""
    # Given: 既定値を保持したクライアントとモック WRP
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(
        api_key="key",
        grammar_file_names="-a-general",
        codec="16K",
        keep_filler_token=True,
        connect_timeout=1000,
        receive_timeout=2000,
        extension="default-tag",
        no_input_timeout=5000,
    )

    # When: override を渡さず stream() を開く
    with patch("amivoice._stream._connect_websocket_transport", return_value=mock_wrp) as mock_build, client.stream() as session:
        session.end()

    # Then: コンストラクタ既定値が RecognitionParams として WRP transport builder に渡される
    params = mock_build.call_args.args[1]
    assert params.grammar_file_names == "-a-general"
    assert params.codec == "16K"
    assert params.keep_filler_token is True
    assert params.connect_timeout == 1000
    assert params.receive_timeout == 2000
    assert params.extension == "default-tag"
    assert params.no_input_timeout == 5000


def test_AmiVoiceClient_stream_connection_failed_raises_error() -> None:
    """WRP 接続失敗のとき ConnectionFailedError が送出されることを確認する。"""
    # Given: 接続失敗を模倣する WRP トランスポートファクトリ
    client = AmiVoiceClient(api_key="key")

    # When / Then: stream() の with ブロック入口で ConnectionFailedError が送出される
    with (
        patch("amivoice._stream._connect_websocket_transport", side_effect=ConnectionFailedError("connect failed")),
        pytest.raises(ConnectionFailedError),
        client.stream(),
    ):
        pass


def test_AmiVoiceClient_stream_start_rejected_invalid_raise_RecognitionError() -> None:
    """開始確認が失敗しても受信スレッドと接続を閉じる"""
    # Given: サーバーが開始を拒否する接続
    mock_wrp = make_websocket_transport()
    mock_wrp.send_text.side_effect = lambda _: mock_wrp._messages.put("s resume failed")
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)
    # When / Then: 開始拒否の例外が伝播する
    with pytest.raises(RecognitionError, match="resume failed"), client.stream():
        pass
    mock_wrp.close.assert_called_once()


def test_AmiVoiceClient_stream_immediate_event_valid_return_event() -> None:
    """開始確認直後のイベントを受信キューで取りこぼさない"""
    # Given: 開始と同時に通知するサーバー
    mock_wrp = make_websocket_transport()
    original = mock_wrp.send_text.side_effect

    def emit(command: str) -> None:
        """開始コマンド送信直後に通知を返す"""
        original(command)
        if command.startswith("s "):
            mock_wrp._messages.put("Q ready")

    mock_wrp.send_text.side_effect = emit
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)
    # When: 開始直後の通知を取得する
    with client.stream() as session:
        event = next(session.events(timeout=1))
        session.end()
    # Then: 開始処理のイベントも届く
    assert event.notification.event_message == "ready"


def test_AmiVoiceClient_stream_write_after_end_raises_recognition_error() -> None:
    """end() 後に write() を呼ぶと RecognitionError が送出されることを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When / Then: end() 後の write() は RecognitionError を送出する
    with client.stream() as session:
        session.end()
        with pytest.raises(RecognitionError, match="ended"):
            session.write(b"too late")


def test_AmiVoiceClient_stream_enter_escape_hatch_works() -> None:
    """StreamConnectionManager.enter escape hatch が __enter__ と同等に動くことを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: with ブロックを使わず manager.enter() / manager.__exit__() を直接呼ぶ
    manager = client.stream()
    session = manager.enter()
    try:
        assert isinstance(session, StreamSession)
        session.end()
    finally:
        manager.__exit__(None, None, None)

    # Then: disconnect が1回呼ばれている
    mock_wrp.close.assert_called_once()


def test_AmiVoiceClient_stream_events_blocking_yields_until_end() -> None:
    """session.events() が end() の終端マーカーまでブロッキングでイベントを yield することを確認する。"""
    # Given: 2件の結果を返すモック WRP トランスポート
    mock_wrp = make_websocket_transport(['{"text": "part1"}', '{"text": "part2"}'])
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: end() 後に events() を消費する
    with client.stream() as session:
        session.end()
        events = list(session.events())

    # Then: partial/final を含む全イベントが順序どおりに返り、final が2件
    final_events = [e for e in events if e.is_final]
    assert [e.text for e in final_events] == ["part1", "part2"]
    assert all(e.type == "final" for e in final_events)


def test_AmiVoiceClient_stream_partial_event_valid_return_stream_event() -> None:
    """途中結果と確定結果の受信順を維持する"""
    # Given: 途中結果を返すサーバー
    mock_wrp = make_websocket_transport()
    original = mock_wrp.send_text.side_effect

    def emit(command: str) -> None:
        """送信終了時に途中結果を先に返す"""
        if command == "e":
            mock_wrp._messages.put("U こんに")
        original(command)

    mock_wrp.send_text.side_effect = emit
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)
    # When: 全イベントを取得する
    with client.stream() as session:
        session.end()
        events = list(session.events())
    # Then: 最初は途中結果、最後は確定結果
    assert events[0].type == "partial"
    assert events[0].text == "こんに"
    assert events[0].is_partial
    assert events[-1].type == "final"


def test_AmiVoiceClient_stream_notifications_valid_return_stream_events() -> None:
    """発話開始・終了・通知を直接イベントへ変換する"""
    # Given: 発話イベントを返すサーバー
    mock_wrp = make_websocket_transport()
    original = mock_wrp.send_text.side_effect

    def emit(command: str) -> None:
        """終了時に発話イベントを返す"""
        if command == "e":
            for message in ("S 100", "E 500", "Q ready", 'A {"text":"hello"}'):
                mock_wrp._messages.put(message)
        original(command)

    mock_wrp.send_text.side_effect = emit
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)
    # When: 全イベントを取得する
    with client.stream() as session:
        session.end()
        events = list(session.events())
    # Then: 発話時間と通知を保持する
    by_type = {event.type: event for event in events}
    assert by_type["utterance_started"].utterance.time == 0
    assert next(event for event in events if event.type == "utterance_started").utterance.time == 100
    assert by_type["utterance_ended"].utterance.time == 500
    assert by_type["notification"].notification.event_id == "Q"


def test_AmiVoiceClient_stream_events_timeout_invalid_raise_RecognitionError() -> None:
    """イベント未到着の待機だけをタイムアウトさせる"""
    # Given: イベントを返さない接続
    mock_wrp = make_websocket_transport(results=[])
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)
    # When / Then: 終了前のイベント待機はタイムアウトする
    with client.stream() as session:
        with pytest.raises(RecognitionError, match="Timed out waiting for stream event"):
            next(session.events(timeout=0.01))
        session.end()


def test_AmiVoiceClient_stream_end_pending_result_invalid_raise_RecognitionError() -> None:
    """終了確認が届いても未確定発話があればタイムアウトする"""
    # Given: 確定結果を返さないサーバー
    mock_wrp = make_websocket_transport(results=[])
    original = mock_wrp.send_text.side_effect

    def emit(command: str) -> None:
        """終了時に未確定発話を残す"""
        if command == "e":
            mock_wrp._messages.put("S 100")
        original(command)

    mock_wrp.send_text.side_effect = emit
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)
    # When / Then: 未確定結果の待機はタイムアウトする
    with client.stream() as session, pytest.raises(RecognitionError, match="Timed out waiting for remaining"):
        session.end(timeout=0.01)


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "value", "expected"),
    [
        ("complete_timeout", "completeTimeout", 5000, "5000"),
        ("wildcard_model_penalty", "wildcardModelPenalty", 4.0, "4.0"),
    ],
)
def test_AmiVoiceClient_transcribe_rule_grammar_parameter_constructor_default_passes_string(
    parameter_name: str,
    wire_name: str,
    value: int | float,
    expected: str,
) -> None:
    """コンストラクタのルールグラマ専用パラメータが HRP 電文境界 に渡ることを確認する"""
    # Given: ルールグラマ専用パラメータを設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, **{parameter_name: value})

    # When: 音声認識を実行する
    client.transcribe(b"audio-data")

    # Then: 対応するHRP 電文境界へ文字列値が渡る
    assert http_wire_values(mock_hrp)[wire_name] == expected


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "default_value", "override_value", "expected"),
    [
        ("complete_timeout", "completeTimeout", 5000, 7000, "7000"),
        ("wildcard_model_penalty", "wildcardModelPenalty", 4.0, 5.5, "5.5"),
    ],
)
def test_AmiVoiceClient_transcribe_rule_grammar_parameter_override_passes_string(
    parameter_name: str,
    wire_name: str,
    default_value: int | float,
    override_value: int | float,
    expected: str,
) -> None:
    """Transcribe のルールグラマ専用パラメータ override が既定値を上書きすることを確認する"""
    # Given: 既定値を設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, **{parameter_name: default_value})

    # When: 音声認識時にルールグラマ専用パラメータを上書きする
    client.transcribe(b"audio-data", **{parameter_name: override_value})

    # Then: 上書きした文字列値が対応するHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)[wire_name] == expected


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "value", "expected"),
    [
        ("complete_timeout", "completeTimeout", 5000, "5000"),
        ("wildcard_model_penalty", "wildcardModelPenalty", 4.0, "4.0"),
    ],
)
def test_AmiVoiceClient_stream_rule_grammar_parameter_constructor_default_passes_string(
    parameter_name: str,
    wire_name: str,
    value: int | float,
    expected: str,
) -> None:
    """コンストラクタのルールグラマ専用パラメータが WRP protocol に渡ることを確認する"""
    # Given: ルールグラマ専用パラメータを設定したクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", **{parameter_name: value})

    # When: ストリーミングセッションを開始して終了する
    with patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp), client.stream() as session:
        session.end()

    # Then: 対応するWRP protocolへ文字列値が渡る
    assert_wrp_parameter(mock_wrp, wire_name, expected)


@pytest.mark.parametrize(
    ("parameter_name", "wire_name", "default_value", "override_value", "expected"),
    [
        ("complete_timeout", "completeTimeout", 5000, 7000, "7000"),
        ("wildcard_model_penalty", "wildcardModelPenalty", 4.0, 5.5, "5.5"),
    ],
)
def test_AmiVoiceClient_stream_rule_grammar_parameter_override_passes_string(
    parameter_name: str,
    wire_name: str,
    default_value: int | float,
    override_value: int | float,
    expected: str,
) -> None:
    """Stream のルールグラマ専用パラメータ override が既定値を上書きすることを確認する"""
    # Given: 既定値を設定したクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", **{parameter_name: default_value})

    # When: ストリーミング開始時にルールグラマ専用パラメータを上書きする
    with (
        patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp),
        client.stream(**{parameter_name: override_value}) as session,
    ):
        session.end()

    # Then: 上書きした文字列値が対応するWRP protocolへ渡る
    assert_wrp_parameter(mock_wrp, wire_name, expected)


@pytest.mark.parametrize(
    ("selected_channel", "expected"),
    [(0, "selectedChannel=0"), ((0, 1), "selectedChannel=0-1")],
)
def test_AmiVoiceClient_transcribe_selected_channel_valid_passes_audio_filter_properties(
    selected_channel: int | tuple[int, int],
    expected: str,
) -> None:
    """selected_channelの単一・範囲指定がHRPへ渡ることを確認する"""
    # Given: 型付きチャネル指定を設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, selected_channel=selected_channel)

    # When: HTTP認識を実行する
    client.transcribe(b"audio-data")

    # Then: audioFilterPropertiesのselectedChannel形式がHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["audioFilterProperties"] == expected


def test_AmiVoiceClient_transcribe_audio_filter_properties_raw_valid_passes_unchanged() -> None:
    """rawのaudio_filter_propertiesがHRPへそのまま渡ることを確認する"""
    # Given: raw音声フィルタプロパティを設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        hrp_transport=mock_hrp,
        audio_filter_properties="selectedChannel=0-1",
    )

    # When: HTTP認識を実行する
    client.transcribe(b"audio-data")

    # Then: raw文字列がHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["audioFilterProperties"] == "selectedChannel=0-1"


def test_AmiVoiceClient_transcribe_selected_channel_override_valid_passes_audio_filter_properties() -> None:
    """transcribeのselected_channel overrideがHRPへ渡ることを確認する"""
    # Given: 音声フィルタプロパティを指定していないHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When: 呼び出し時にチャネル範囲を指定してHTTP認識を実行する
    client.transcribe(b"audio-data", selected_channel=(1, 2))

    # Then: overrideのselectedChannel形式がHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["audioFilterProperties"] == "selectedChannel=1-2"


def test_AmiVoiceClient_transcribe_selected_channel_override_none_valid_clears_constructor_setting() -> None:
    """transcribeのselected_channel=Noneでコンストラクタの指定が解除されることを確認する"""
    # Given: コンストラクタでチャネルを指定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, selected_channel=1)

    # When: 呼び出し時にselected_channel=Noneを指定してHTTP認識を実行する
    client.transcribe(b"audio-data", selected_channel=None)

    # Then: 音声フィルタプロパティはHRPへ渡らない
    assert "audioFilterProperties" not in http_wire_values(mock_hrp)


def test_AmiVoiceClient_transcribe_audio_filter_properties_override_valid_replaces_selected_channel() -> None:
    """transcribeのraw文字列overrideでコンストラクタのselected_channelが上書きされることを確認する"""
    # Given: コンストラクタでチャネルを指定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, selected_channel=1)

    # When: 呼び出し時にraw文字列を指定してHTTP認識を実行する
    client.transcribe(b"audio-data", audio_filter_properties="selectedChannel=2")

    # Then: 呼び出し時のraw文字列だけがHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["audioFilterProperties"] == "selectedChannel=2"


def test_AmiVoiceClient_transcribe_audio_filter_properties_override_none_valid_clears_constructor_setting() -> None:
    """transcribeのaudio_filter_properties=Noneでコンストラクタの指定が解除されることを確認する"""
    # Given: コンストラクタでraw文字列を指定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, audio_filter_properties="selectedChannel=1")

    # When: 呼び出し時にaudio_filter_properties=Noneを指定してHTTP認識を実行する
    client.transcribe(b"audio-data", audio_filter_properties=None)

    # Then: 音声フィルタプロパティはHRPへ渡らない
    assert "audioFilterProperties" not in http_wire_values(mock_hrp)


@pytest.mark.parametrize(
    "selected_channel",
    [-1, (-1, 0), (1, 0), (0, 0), (2, 2), (0, 1, 2), True],
)
def test_AmiVoiceClient_selected_channel_invalid_raise_ConfigurationError(selected_channel: object) -> None:
    """不正なselected_channelでConfigurationErrorが送出されることを確認する"""
    # Given: 不正なチャネル番号または範囲
    # When / Then: クライアント生成でConfigurationErrorが送出される
    with pytest.raises(ConfigurationError, match="selected_channel"):
        AmiVoiceClient(api_key="key", selected_channel=selected_channel)  # type: ignore[arg-type]


def test_AmiVoiceClient_transcribe_selected_channel_same_range_override_invalid_raise_ConfigurationError() -> None:
    """transcribeの開始と終了が同じチャネル範囲でConfigurationErrorが送出されることを確認する"""
    # Given: 音声フィルタ指定を持たないHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When / Then: 呼び出し時に(0, 0)を指定すると送信前にConfigurationErrorになる
    with pytest.raises(ConfigurationError, match="start and end must be different"):
        client.transcribe(b"audio-data", selected_channel=(0, 0))
    mock_hrp.transcribe.assert_not_called()


def test_AmiVoiceClient_selected_channel_and_raw_properties_invalid_raise_ConfigurationError() -> None:
    """selected_channelとraw文字列の同時指定でConfigurationErrorが送出されることを確認する"""
    # Given: 型付き指定とraw指定を同時に指定したクライアント設定
    # When / Then: クライアント生成でConfigurationErrorが送出される
    with pytest.raises(ConfigurationError, match="selected_channel and audio_filter_properties"):
        AmiVoiceClient(api_key="key", selected_channel=0, audio_filter_properties="selectedChannel=1")


def test_AmiVoiceClient_transcribe_selected_channel_and_raw_override_invalid_raise_ConfigurationError() -> None:
    """transcribeの型付き指定とraw指定の同時指定でConfigurationErrorが送出されることを確認する"""
    # Given: 音声フィルタ指定を持たないクライアント
    client = AmiVoiceClient(api_key="key")

    # When / Then: 呼び出し時に型付き指定とraw指定を同時に指定するとエラーになる
    with pytest.raises(ConfigurationError, match="selected_channel and audio_filter_properties"):
        client.transcribe(b"audio-data", selected_channel=0, audio_filter_properties="selectedChannel=1")


def test_AmiVoiceClient_transcribe_profile_words_sequence_valid_passes_serialized_string() -> None:
    """コンストラクタのProfileWordシーケンスがHRPへシリアライズされることを確認する"""
    # Given: ProfileWordシーケンスを設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        hrp_transport=mock_hrp,
        profile_words=(ProfileWord(written="AmiVoice", spoken="あみぼいす"),),
    )

    # When: HTTP認識を実行する
    client.transcribe(b"audio-data")

    # Then: profileWordsのワイヤー形式がHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["profileWords"] == "AmiVoice あみぼいす"


def test_AmiVoiceClient_transcribe_profile_words_override_valid_passes_serialized_string() -> None:
    """transcribeのProfileWordシーケンスoverrideがHRPへシリアライズされることを確認する"""
    # Given: 既定のprofile_wordsを持つHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(
        api_key="key",
        hrp_transport=mock_hrp,
        profile_words="default word",
    )

    # When: ProfileWordシーケンスでHTTP認識時の設定を上書きする
    client.transcribe(
        b"audio-data",
        profile_words=(ProfileWord(written="WWW", spoken="とりぷるだぶる"),),
    )

    # Then: overrideのワイヤー形式がHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["profileWords"] == "WWW とりぷるだぶる"


@pytest.mark.parametrize("empty_words", [(), []])
def test_AmiVoiceClient_transcribe_profile_words_empty_sequence_valid_skip_parameter(empty_words: Sequence[ProfileWord]) -> None:
    """空のProfileWordシーケンスでHRPのprofileWordsを設定しないことを確認する"""
    # Given: 空のProfileWordシーケンスを設定したHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, profile_words=empty_words)

    # When: HTTP認識を実行する
    client.transcribe(b"audio-data")

    # Then: 空文字列のprofileWordsは送られない
    assert "profileWords" not in http_wire_values(mock_hrp)


def test_AmiVoiceClient_transcribe_profile_words_empty_override_valid_clear_default() -> None:
    """空のProfileWordシーケンスoverrideが既定のprofile_wordsを送らないことを確認する"""
    # Given: 既定のprofile_wordsを持つHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, profile_words="default word")

    # When: 空のProfileWordシーケンスでHTTP認識時の設定を上書きする
    client.transcribe(b"audio-data", profile_words=())

    # Then: 既定値も空文字列もHRP 電文境界へ渡らない
    assert "profileWords" not in http_wire_values(mock_hrp)


def test_AmiVoiceClient_stream_profile_words_empty_sequence_valid_skip_protocol() -> None:
    """streamの空のProfileWordシーケンスでWRPのprofileWordsを設定しないことを確認する"""
    # Given: クライアントとモックWRP
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key")

    # When: 空のProfileWordシーケンスでストリーミングセッションを開始する
    with (
        patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp),
        client.stream(profile_words=[]) as session,
    ):
        session.end()

    # Then: 空文字列のprofileWordsは送られない
    assert_wrp_parameter_absent(mock_wrp, "profileWords")


def test_AmiVoiceClient_stream_profile_words_sequence_valid_passes_serialized_string() -> None:
    """streamのProfileWordシーケンスがWRPへシリアライズされることを確認する"""
    # Given: ProfileWordシーケンスを指定するクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key")

    # When: ProfileWordシーケンスでストリーミングセッションを開始する
    with (
        patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp),
        client.stream(profile_words=(ProfileWord(written="AmiVoice", spoken="あみぼいす"),)) as session,
    ):
        session.end()

    # Then: profileWordsのワイヤー形式がWRP protocolへ渡る
    assert_wrp_parameter(mock_wrp, "profileWords", "AmiVoice あみぼいす")


def test_AmiVoiceClient_transcribe_profile_id_without_colon_warns_and_passes_as_is() -> None:
    """コロンなしのprofile_idで警告し、値を書き換えずに送ることを確認する"""
    # Given: コロンなしのprofile_idを設定したHRPクライアント
    mock_hrp = make_http_transport()
    with pytest.warns(UserWarning, match="profile_id"):
        client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, profile_id="myprofile")

    # When: HTTP認識を実行する
    with pytest.warns(UserWarning, match="profile_id"):
        client.transcribe(b"audio-data")

    # Then: profileIdはコロンを付与せずHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["profileId"] == "myprofile"


def test_AmiVoiceClient_transcribe_profile_id_override_without_colon_warns() -> None:
    """transcribeのコロンなしprofile_id overrideで警告することを確認する"""
    # Given: コロン付きの既定profile_idを持つHRPクライアント
    mock_hrp = make_http_transport()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, profile_id=":default-profile")

    # When: コロンなしのprofile_idでHTTP認識時の設定を上書きする
    with pytest.warns(UserWarning, match="profile_id"):
        client.transcribe(b"audio-data", profile_id="override-profile")

    # Then: override値は書き換えられずHRP 電文境界へ渡る
    assert http_wire_values(mock_hrp)["profileId"] == "override-profile"


@pytest.mark.filterwarnings("error")
def test_AmiVoiceClient_stream_profile_id_with_colon_no_warning_passes_as_is() -> None:
    """streamのコロン付きprofile_idが警告なしでWRPへ渡ることを確認する"""
    # Given: コロン付きのprofile_idを設定したクライアント
    mock_wrp = make_websocket_transport()
    client = AmiVoiceClient(api_key="key", profile_id=":myprofile")

    # When: ストリーミングセッションを開始する
    with (
        patch("amivoice._stream.WebSocketTransport", return_value=mock_wrp),
        client.stream() as session,
    ):
        session.end()

    # Then: profileIdがそのままWRP protocolへ渡る
    assert_wrp_parameter(mock_wrp, "profileId", ":myprofile")
