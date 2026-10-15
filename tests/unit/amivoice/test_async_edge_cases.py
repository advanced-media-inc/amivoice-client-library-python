"""非同期HTTPの設定、失敗、待機境界を追加で検証する"""

import inspect

import pytest

from amivoice import (
    AmiVoiceAsyncClient,
    AsyncHttpApiError,
    AsyncJobTimeoutError,
    ConfigurationError,
    ConnectionFailedError,
    RecognitionSettings,
)
from amivoice._async_models import parse_job
from amivoice._params import RecognitionParams
from amivoice._request_parameters import _request_values

from .test_async_client import RecordingTransport, completed, queued


@pytest.mark.parametrize("field", ["connect_timeout", "receive_timeout"])
def test_client_none_transport_timeout_invalid_raise_ConfigurationError(field: str) -> None:
    """通信設定はNoneによる解除を認めない"""
    # Given: 非負整数でない通信待機値
    # When / Then: 接続生成前に設定エラー
    with pytest.raises(ConfigurationError):
        AmiVoiceAsyncClient(api_key="dummy", **{field: None})


@pytest.mark.parametrize("operation", ["submit", "get_job", "wait"])
def test_client_override_none_timeout_invalid_raise_ConfigurationError(operation: str) -> None:
    """上書きでも通信待機Noneを送らない"""
    # Given: 通信を許可しないクライアント
    transport = RecordingTransport([])
    client = AmiVoiceAsyncClient(
        settings=RecognitionSettings(grammar_file_names="-a-general"), api_key="dummy", transport=transport
    )
    # When / Then: 全操作で通信前に拒否
    with pytest.raises(ConfigurationError):
        getattr(client, operation)(b"audio" if operation == "submit" else "job1", receive_timeout=None)
    assert not transport.calls


def test_wait_huge_number_invalid_raise_ConfigurationError() -> None:
    """floatへ変換不能な整数でも安全な設定エラー"""
    # Given: 異常に大きい待機時間
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([]))
    # When / Then: OverflowErrorを漏らさない
    with pytest.raises(ConfigurationError):
        client.wait("job1", timeout=10**1000)


@pytest.mark.parametrize("session_id", ["..", "job/other", "job\\other"])
def test_submit_invalid_returned_id_invalid_raise_AsyncHttpApiError(session_id: str) -> None:
    """安全に再開できない受付IDは不正応答"""
    # Given: 有効な音声に対する壊れた受付応答
    transport = RecordingTransport([{"sessionid": session_id, "text": "..."}])
    client = AmiVoiceAsyncClient(
        settings=RecognitionSettings(grammar_file_names="-a-general"), api_key="dummy", transport=transport
    )
    # When / Then: 受付成功としない
    with pytest.raises(AsyncHttpApiError):
        client.submit(b"audio")


def test_wait_parse_deadline_edge_raise_with_completed_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """解析中に締め切りへ到達しても成功として返さない"""
    # Given: 解析処理によって時間が進む仮想時計
    clock = [0.0]
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([completed()]))
    monkeypatch.setattr(client, "_clock", lambda: clock[0])

    def delayed_parse(body: bytes, session_id: str):
        snapshot = parse_job(body, session_id)
        clock[0] = 2.0
        return snapshot

    monkeypatch.setattr("amivoice.async_client.parse_job", delayed_parse)
    # When / Then: 最後に解析できた状態を添付する
    with pytest.raises(AsyncJobTimeoutError) as caught:
        client.wait("job1", timeout=1)
    assert caught.value.snapshot.status == "completed"


def test_submit_network_failure_invalid_raise_without_retry() -> None:
    """POST通信失敗後に重複ジョブを作らない"""
    # Given: 認証情報を含む接続例外
    transport = RecordingTransport([OSError("dummy-key proxy-password connection lost")])
    client = AmiVoiceAsyncClient(
        settings=RecognitionSettings(grammar_file_names="-a-general"), api_key="dummy-key", transport=transport
    )
    # When / Then: 安全な説明と受付済み不明の警告を返す
    with pytest.raises(ConnectionFailedError) as caught:
        client.submit(b"audio")
    assert len(transport.calls) == 1
    assert "may have been accepted" in str(caught.value)
    assert "dummy-key" not in str(caught.value) and "proxy-password" not in str(caught.value)


@pytest.mark.parametrize("body", [b"not-json", b"\xff", b'{"status":"","session_id":"job1"}'])
def test_wait_raise_disabled_malformed_invalid_raise_AsyncHttpApiError(body: bytes) -> None:
    """raise_on_error=Falseでも壊れた応答は例外"""
    # Given: HTTP200の不正応答
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([(200, body)]))
    # When / Then: 正常な結果を捏造しない
    with pytest.raises(AsyncHttpApiError):
        client.wait("job1", raise_on_error=False)


def test_get_job_error_state_valid_return_snapshot() -> None:
    """状態取得単体はジョブ失敗を例外にしない"""
    # Given: サーバーの失敗状態
    response = {**queued("error"), "error_message": "failure"}
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([response]))
    # When: 状態を観測する
    snapshot = client.get_job("job1")
    # Then: 詳細を利用者が確認できる
    assert snapshot.is_error and snapshot.error_message == "failure"


@pytest.mark.parametrize("field", ["complete_timeout", "wildcard_model_penalty", "result_updated_interval", "no_input_timeout"])
def test_async_domain_unsupported_setting_invalid_raise_ConfigurationError(field: str) -> None:
    """HTTP共通表の再利用で非対応項目を送信しない"""
    # Given: 明示0も非対応指定に含まれる
    params = RecognitionParams(grammar_file_names="-a-general", **{field: 0})
    # When / Then: 本文生成前に拒否
    with pytest.raises(ConfigurationError):
        _request_values(params, "async_http")


def test_client_analysis_options_valid_return_absent_signature() -> None:
    """話者設定はRecognitionSettingsだけで公開し感情分析は未対応とする"""
    # Given: 公開APIの署名
    for method in (AmiVoiceAsyncClient, AmiVoiceAsyncClient.submit):
        # When: 専用の直接引数を調べる
        parameters = inspect.signature(method).parameters
        # Then: 直接引数を増やさず型付き設定だけを提供する
        assert "speaker_diarization" not in parameters
        assert "sentiment_analysis" not in parameters
    settings_parameters = inspect.signature(RecognitionSettings).parameters
    assert {"speaker_diarization", "diarization_min_speaker", "diarization_max_speaker"} <= settings_parameters.keys()
    assert "sentiment_analysis" not in settings_parameters


@pytest.mark.parametrize("segmenter", ["useDiarizer=0", "diarizerAlpha=1e-20", "diarizerTransitionBias=0"])
def test_client_segmenter_diarization_invalid_raise_alternative(segmenter: str) -> None:
    """同期向けの話者設定は無効指定も非同期で拒否する"""
    # Given: 別方式の話者設定
    settings = RecognitionSettings(grammar_file_names="-a-general", segmenter_properties=segmenter)
    # When / Then: 非同期の代替APIを案内する
    with pytest.raises(ConfigurationError, match=r"RecognitionSettings\(speaker_diarization=True\)"):
        AmiVoiceAsyncClient(api_key="dummy", settings=settings)


def test_submit_segmenter_vad_lid_valid_return_parameters() -> None:
    """非同期でVADとLIDは引き続き利用できる"""
    # Given: 話者設定以外のセグメンター
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}])
    client = AmiVoiceAsyncClient(
        api_key="dummy",
        transport=transport,
        settings=RecognitionSettings(grammar_file_names="-a-general", segmenter_properties="threshold=5000 useLid=1"),
    )
    # When: ジョブを登録する
    client.submit(b"audio")
    # Then: セグメンター設定を送信する
    assert b"segmenterProperties=threshold%3D5000%20useLid%3D1" in transport.calls[0][3]
