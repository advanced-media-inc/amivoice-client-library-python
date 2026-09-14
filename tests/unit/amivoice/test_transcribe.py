# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false, reportUnusedCallResult=false

"""transcribe フリー関数のユニットテスト。"""

import os
import threading
from unittest.mock import MagicMock, patch

import pytest

from amivoice._segmenter import SegmenterProperties
from amivoice.client import _DEFAULT_HRP_URL, transcribe
from amivoice.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ConnectionFailedError,
    RecognitionError,
)
from amivoice.models import RecognitionResult


def _make_mock_hrp(result_json: str = '{"text": "hello"}', *, connect_ok: bool = True) -> MagicMock:
    """テスト用のモック HRP オブジェクトを生成する。"""
    mock_hrp = MagicMock()
    mock_hrp.connect.return_value = connect_ok
    mock_hrp.feedDataResume.return_value = True
    mock_hrp.feedData.return_value = True
    mock_hrp.getLastMessage.return_value = "error"

    def set_listener(listener: object) -> None:
        mock_hrp.listener = listener

    def finalize_result() -> bool:
        mock_hrp.listener.resultFinalized(result_json)
        return True

    mock_hrp.setListener.side_effect = set_listener
    mock_hrp.feedDataPause.side_effect = finalize_result
    return mock_hrp


def test_transcribe_success_valid_return_result() -> None:
    """Transcribe が正常に完了した場合に RecognitionResult が返ることを確認する。"""
    # Given: 全操作が成功するモック HRP
    mock_hrp = _make_mock_hrp('{"text": "hello"}')

    # When: transcribe フリー関数を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        result = transcribe(b"audio-data", api_key="test-key")

    # Then: 認識結果が返る
    assert result == RecognitionResult(raw='{"text": "hello"}', data={"text": "hello"})
    mock_hrp.connect.assert_called_once()
    mock_hrp.disconnect.assert_called_once()


def test_transcribe_default_api_url_valid_uses_default_url() -> None:
    """api_url を省略した場合にデフォルト URL が使用されることを確認する。"""
    # Given: モック HRP とデフォルト URL
    mock_hrp = _make_mock_hrp()

    # When: api_url を指定せずに transcribe を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        transcribe(b"audio-data", api_key="test-key")

    # Then: デフォルト URL が setServerURL に渡される
    mock_hrp.setServerURL.assert_called_once_with(_DEFAULT_HRP_URL)


def test_transcribe_custom_api_url_valid_uses_given_url() -> None:
    """api_url を指定した場合にその URL が使用されることを確認する。"""
    # Given: カスタム URL
    custom_url = "https://custom.example.com/v1/recognize"
    mock_hrp = _make_mock_hrp()

    # When: カスタム api_url を指定して transcribe を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        transcribe(b"audio-data", api_key="test-key", api_url=custom_url)

    # Then: カスタム URL が setServerURL に渡される
    mock_hrp.setServerURL.assert_called_once_with(custom_url)


def test_transcribe_segmenter_valid_passes_generated_parameter() -> None:
    """モジュールレベル transcribe の型付き設定が HRP に渡されることを確認する。"""
    # Given: 型付きセグメンター設定とモック HRP
    mock_hrp = _make_mock_hrp()
    properties = SegmenterProperties(speaker_diarization=True)

    # When: 型付き設定を指定して transcribe を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        transcribe(b"audio-data", api_key="test-key", segmenter=properties)

    # Then: 生成された segmenterProperties 文字列が HRP に渡される
    mock_hrp.setSegmenterProperties.assert_called_once_with("useDiarizer=1")


def test_transcribe_confidence_level_valid_passes_repr() -> None:
    """モジュールレベル transcribe の confidence_level が repr 文字列で HRP に渡ることを確認する。"""
    # Given: confidence_level とモック HRP
    mock_hrp = _make_mock_hrp()

    # When: confidence_level を指定して transcribe を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        transcribe(b"audio-data", api_key="test-key", confidence_level=0.3)

    # Then: 小数表記を維持した文字列が setter に渡される
    mock_hrp.setConfidenceLevel.assert_called_once_with("0.3")


def test_transcribe_processing_time_params_valid_passes_strings() -> None:
    """モジュールレベル transcribe の処理時間制御パラメータが文字列で HRP に渡ることを確認する"""
    # Given: 処理時間制御パラメータとモック HRP
    mock_hrp = _make_mock_hrp()

    # When: 処理時間制御パラメータを指定して transcribe を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        transcribe(
            b"audio-data",
            api_key="test-key",
            complete_timeout=5000,
            wildcard_model_penalty=4.0,
            max_decoding_time=1000,
            max_response_time=2000,
            max_decoding_rate=1.25,
            target_response_time=3000,
            target_decoding_rate=-1.0,
        )

    # Then: 各 setter に対応する文字列が渡る
    mock_hrp.setCompleteTimeout.assert_called_once_with("5000")
    mock_hrp.setWildcardModelPenalty.assert_called_once_with("4.0")
    mock_hrp.setMaxDecodingTime.assert_called_once_with("1000")
    mock_hrp.setMaxResponseTime.assert_called_once_with("2000")
    mock_hrp.setMaxDecodingRate.assert_called_once_with("1.25")
    mock_hrp.setTargetResponseTime.assert_called_once_with("3000")
    mock_hrp.setTargetDecodingRate.assert_called_once_with("-1.0")


def test_transcribe_billing_key_valid_passes_extension() -> None:
    """モジュールレベル transcribe の billing_key が HRP の extension setter に渡ることを確認する"""
    # Given: billing_key とモック HRP
    mock_hrp = _make_mock_hrp()

    # When: billing_key を指定して transcribe を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        transcribe(b"audio-data", api_key="test-key", billing_key="user01")

    # Then: billing_key 用のコンパクト JSON が extension setter に渡る
    mock_hrp.setExtension.assert_called_once_with('{"client_info":{"billing_key":"user01"}}')


def test_transcribe_extension_and_billing_key_invalid_raise_ConfigurationError() -> None:
    """モジュールレベル transcribe で extension と billing_key を同時指定すると ConfigurationError が送出されることを確認する"""
    # Given: 既存 extension と billing_key
    # When / Then: transcribe の設定で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="extension and billing_key"):
        transcribe(
            b"audio-data",
            api_key="test-key",
            extension="legacy-extension",
            billing_key="user01",
        )


def test_transcribe_segmenter_and_raw_properties_invalid_raise_ConfigurationError() -> None:
    """モジュールレベル transcribe で設定を同時指定すると ConfigurationError が送出されることを確認する。"""
    # Given: 型付きセグメンター設定
    properties = SegmenterProperties(threshold=5000)

    # When / Then: 型付き設定と生文字列を同時指定すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="segmenter and segmenter_properties"):
        transcribe(
            b"audio-data",
            api_key="test-key",
            segmenter=properties,
            segmenter_properties="threshold=1000",
        )


def test_transcribe_connection_fails_invalid_raise_ConnectionFailedError() -> None:
    """接続に失敗した場合に ConnectionFailedError が送出されることを確認する。"""
    # Given: connect が失敗するモック HRP
    mock_hrp = _make_mock_hrp(connect_ok=False)

    # When / Then: transcribe を呼び出すと ConnectionFailedError が送出される
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp), pytest.raises(ConnectionFailedError):
        transcribe(b"audio-data", api_key="test-key")


def test_transcribe_server_error_response_invalid_raise_RecognitionError() -> None:
    """サーバーエラーレスポンスが返った場合に RecognitionError が送出されることを確認する。"""
    # Given: エラーレスポンスを返すモック HRP
    mock_hrp = _make_mock_hrp('\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}')

    # When / Then: transcribe を呼び出すと RecognitionError が送出される
    with (
        patch("amivoice.client._Hrp.construct", return_value=mock_hrp),
        pytest.raises(RecognitionError, match="bad request") as exc_info,
    ):
        transcribe(b"audio-data", api_key="test-key")

    assert exc_info.value.result is not None
    assert exc_info.value.result.is_error is True


def test_transcribe_raise_on_error_false_invalid_return_error_result() -> None:
    """raise_on_error=False の場合にエラー結果がそのまま返ることを確認する。"""
    # Given: エラーレスポンスを返すモック HRP
    mock_hrp = _make_mock_hrp('\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}')

    # When: raise_on_error=False で transcribe を呼び出す
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp):
        result = transcribe(b"audio-data", api_key="test-key", raise_on_error=False)

    # Then: 例外は送出されず is_error=True の結果が返る
    assert result.is_error is True
    assert result.data == {"code": "E001", "message": "bad request"}


def test_transcribe_no_api_key_invalid_raise_AuthenticationError() -> None:
    """api_key が未設定かつ環境変数も未設定の場合に AuthenticationError が送出されることを確認する。"""
    # Given: api_key も環境変数も未設定
    # When / Then: transcribe を呼び出すと AuthenticationError が送出される
    with patch.dict("os.environ", {}, clear=True):
        # 環境変数 AMIVOICE_API_KEY が存在しない状態にする
        os.environ.pop("AMIVOICE_API_KEY", None)
        with pytest.raises(AuthenticationError):
            transcribe(b"audio-data")


def test_transcribe_concurrent_calls_valid_independent_connections() -> None:
    """複数スレッドから同時に transcribe を呼び出した場合に各呼び出しが独立して動作することを確認する。"""
    # Given: 各スレッドに独立したモック HRP を返すファクトリ
    call_count = 0
    call_count_lock = threading.Lock()
    results: list[RecognitionResult] = []
    errors: list[Exception] = []

    def make_hrp() -> MagicMock:
        nonlocal call_count
        with call_count_lock:
            call_count += 1
        return _make_mock_hrp(f'{{"text": "result-{call_count}"}}')

    def worker() -> None:
        try:
            result = transcribe(b"audio", api_key="test-key")
            results.append(result)
        except Exception as exc:
            errors.append(exc)

    # When: 4 スレッドから同時に transcribe を呼び出す
    # NOTE: patch はスレッド間で共有される属性を差し替えるためスレッドセーフではない。
    # スレッド起動の外側で 1 度だけ patch を張り、スレッドセーフな make_hrp（ロック保護）で
    # 各スレッドに独立したモックを配る。
    with patch("amivoice.client._Hrp.construct", side_effect=make_hrp):
        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # Then: エラーなし、4 件の認識結果が返る（各呼び出しが独立）
    assert errors == []
    assert len(results) == 4


def test_transcribe_disconnect_called_even_on_error() -> None:
    """認識処理中にエラーが発生した場合でも disconnect が呼ばれることを確認する。"""
    # Given: feedDataResume が失敗するモック HRP
    mock_hrp = MagicMock()
    mock_hrp.connect.return_value = True
    mock_hrp.feedDataResume.return_value = False
    mock_hrp.getLastMessage.return_value = "resume failed"

    # When: transcribe を呼び出すと RecognitionError が送出される
    with patch("amivoice.client._Hrp.construct", return_value=mock_hrp), pytest.raises(RecognitionError):
        transcribe(b"audio-data", api_key="test-key")

    # Then: エラー後も disconnect が呼ばれる（リソースリークなし）
    mock_hrp.disconnect.assert_called_once()
