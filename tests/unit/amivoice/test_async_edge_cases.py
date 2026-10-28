"""非同期HTTPの設定、失敗、待機境界を追加で検証する"""

import inspect
import math

import pytest

from amivoice import (
    AmiVoiceAsyncClient,
    AsyncHttpApiError,
    AsyncJobError,
    AsyncJobSnapshot,
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


@pytest.mark.parametrize("parameter, maximum", [("timeout", 604_800), ("poll_interval", 3_600)])
@pytest.mark.parametrize("value_kind", ["next_float", "next_integer", "huge_float", "huge_integer"])
def test_wait_over_maximum_invalid_raise_ConfigurationError(
    parameter: str, maximum: int, value_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """上限超過を時計参照・通信・待機の前に拒否する"""
    # Given: 上限を超える有限値又はfloatへ変換できない整数
    values = {
        "next_float": math.nextafter(float(maximum), math.inf),
        "next_integer": maximum + 1,
        "huge_float": 1e300,
        "huge_integer": 10**1000,
    }
    transport = RecordingTransport([])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)

    def unexpected_wait(*args: object) -> None:
        raise AssertionError("Invalid settings must be rejected before waiting")

    monkeypatch.setattr(client, "_clock", unexpected_wait)
    monkeypatch.setattr(client, "_sleep", unexpected_wait)
    # When / Then: 生のOverflowErrorではなく設定例外を返す
    with pytest.raises(ConfigurationError, match=parameter):
        client.wait("job1", **{parameter: values[value_kind]})
    assert not transport.calls


@pytest.mark.parametrize("timeout", [604_800, 604_800.0, None])
@pytest.mark.parametrize("poll_interval", [3_600, 3_600.0])
def test_wait_maximum_settings_edge_return_completed(
    timeout: float | None, poll_interval: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    """上限ちょうどの整数・小数と無期限待機を許可する"""
    # Given: 処理中から完了するジョブと実時間を使わない時計
    transport = RecordingTransport([queued(), completed()])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    clock = [0.0]
    sleeps = []
    monkeypatch.setattr(client, "_clock", lambda: clock[0])

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(client, "_sleep", sleep)
    # When: 最大間隔でポーリングする
    snapshot = client.wait("job1", timeout=timeout, poll_interval=poll_interval)
    # Then: 上限値を切り詰めずに使い、Noneだけ期限なしとする
    assert snapshot.status == "completed"
    assert sleeps == [poll_interval]
    assert len(transport.calls) == 2
    assert all(call[-1] == timeout for call in transport.calls)


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


def test_wait_parse_deadline_edge_return_completed_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """解析中に締め切りへ到達しても取得済みの終端結果を返す"""
    # Given: 解析処理によって時間が進む仮想時計
    clock = [0.0]
    client = AmiVoiceAsyncClient(api_key="dummy", transport=RecordingTransport([completed()]))
    monkeypatch.setattr(client, "_clock", lambda: clock[0])

    def delayed_parse(body: bytes, session_id: str) -> AsyncJobSnapshot:
        snapshot = parse_job(body, session_id)
        clock[0] = 2.0
        return snapshot

    monkeypatch.setattr("amivoice.async_client.parse_job", delayed_parse)
    # When: 解析中に期限を超える
    snapshot = client.wait("job1", timeout=1)
    # Then: 取得済みの結果をタイムアウトで失わない
    assert snapshot.status == "completed"
    assert snapshot.recognition.text == "認識"


@pytest.mark.parametrize("arrival", [1.0, 1.1])
@pytest.mark.parametrize("status", ["completed", "error", "recognition_error", "processing"])
@pytest.mark.parametrize("raise_on_error", [True, False])
def test_wait_received_deadline_edge_return_or_raise_latest_snapshot(
    arrival: float, status: str, raise_on_error: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """期限到達時の受信済み終端応答を優先し、非終端は最新状態でタイムアウトする"""
    # Given: queued取得後の応答で期限に達するtransportと仮想時計
    response = completed() if status in ("completed", "recognition_error") else queued(status)
    if status == "error":
        response["error_message"] = "failure"
    elif status == "recognition_error":
        response.update(code="o", message="rejected", text="", segments=[])
    transport = RecordingTransport([queued(), response])
    client = AmiVoiceAsyncClient(api_key="dummy", transport=transport)
    clock = [0.0]
    monkeypatch.setattr(client, "_clock", lambda: clock[0])
    monkeypatch.setattr(client, "_sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    request = transport.request

    def delayed_request(*args, **kwargs) -> tuple[int, bytes]:
        result = request(*args, **kwargs)
        if len(transport.calls) == 2:
            clock[0] = arrival
        return result

    monkeypatch.setattr(transport, "request", delayed_request)
    # When / Then: 受信済みの最新状態を使い、追加のGETを行わない
    if status == "processing":
        with pytest.raises(AsyncJobTimeoutError) as caught:
            client.wait("job1", timeout=1, poll_interval=0.5, raise_on_error=raise_on_error)
        assert caught.value.snapshot.data == response
        assert caught.value.session_id == "job1"
    elif status in ("error", "recognition_error") and raise_on_error:
        with pytest.raises(AsyncJobError) as caught:
            client.wait("job1", timeout=1, poll_interval=0.5, raise_on_error=raise_on_error)
        assert caught.value.snapshot.data == response
    else:
        snapshot = client.wait("job1", timeout=1, poll_interval=0.5, raise_on_error=raise_on_error)
        assert snapshot.data == response
        assert snapshot.is_terminal
        assert snapshot.is_error == (status != "completed")
    assert len(transport.calls) == 2


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
    """話者・感情設定はRecognitionSettingsだけで公開する"""
    # Given: 公開APIの署名
    for method in (AmiVoiceAsyncClient, AmiVoiceAsyncClient.submit):
        # When: 専用の直接引数を調べる
        parameters = inspect.signature(method).parameters
        # Then: 直接引数を増やさず型付き設定だけを提供する
        assert "speaker_diarization" not in parameters
        assert "sentiment_analysis" not in parameters
    settings_parameters = inspect.signature(RecognitionSettings).parameters
    assert {"speaker_diarization", "diarization_min_speaker", "diarization_max_speaker"} <= settings_parameters.keys()
    assert "sentiment_analysis" in settings_parameters


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
