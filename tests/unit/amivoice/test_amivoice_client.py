# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false, reportUnusedCallResult=false

"""AmiVoiceClient のユニットテスト。"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from amivoice._segmenter import SegmenterProperties
from amivoice._stream import StreamConnectionManager, StreamSession
from amivoice.client import _DEFAULT_HRP_URL, _DEFAULT_WRP_URL, AmiVoiceClient
from amivoice.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ConnectionFailedError,
    RecognitionError,
)
from amivoice.models import RecognitionResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_hrp(result_json: str = '{"text": "hello"}', *, connect_ok: bool = True) -> MagicMock:
    """テスト用のモック HRP トランスポートを生成する。

    ``feedDataPause`` を呼び出すと ``setListener`` で登録されたリスナーに
    ``resultFinalized`` を送信してから True を返す。
    """
    mock_hrp = MagicMock()
    mock_hrp.connect.return_value = connect_ok
    mock_hrp.feedDataResume.return_value = True
    mock_hrp.feedData.return_value = True
    mock_hrp.getLastMessage.return_value = "error"

    def set_listener(listener: object) -> None:
        mock_hrp._listener = listener

    def finalize_result() -> bool:
        mock_hrp._listener.resultFinalized(result_json)
        return True

    mock_hrp.setListener.side_effect = set_listener
    mock_hrp.feedDataPause.side_effect = finalize_result
    return mock_hrp


def _make_mock_wrp(results: list[str] | None = None, *, connect_ok: bool = True) -> MagicMock:
    """テスト用のモック WRP トランスポートを生成する。

    ``feedDataPause`` を呼び出すと登録済みリスナーに各 ``resultFinalized`` を送信し、
    以後 ``getWaitingResults`` が 0 を返す。
    ``feedDataResume`` は True を返す。
    """
    if results is None:
        results = ['{"text": "stream result"}']

    mock_wrp = MagicMock()
    mock_wrp.connect.return_value = connect_ok
    mock_wrp.feedDataResume.return_value = True
    mock_wrp.feedData.return_value = True
    mock_wrp.getLastMessage.return_value = "error"
    mock_wrp.getWaitingResults.return_value = 0

    def set_listener(listener: object) -> None:
        mock_wrp._listener = listener

    def finalize_all() -> bool:
        for r in results:
            mock_wrp._listener.resultFinalized(r)
        return True

    mock_wrp.setListener.side_effect = set_listener
    mock_wrp.feedDataPause.side_effect = finalize_all
    return mock_wrp


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
    mock_hrp = _make_mock_hrp('{"text": "hello world"}')
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When
    result = client.transcribe(b"audio-data")

    # Then
    assert result == RecognitionResult(raw='{"text": "hello world"}', data={"text": "hello world"})


def test_AmiVoiceClient_transcribe_does_not_call_connect_on_transport() -> None:
    """注入された hrp_transport では connect/disconnect が呼ばれないことを確認する。"""
    # Given: テスト注入パスでは connect/disconnect 不要
    mock_hrp = _make_mock_hrp()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When
    client.transcribe(b"audio-data")

    # Then: transport injection 経路では connect/disconnect を呼ばない
    mock_hrp.connect.assert_not_called()
    mock_hrp.disconnect.assert_not_called()


def test_AmiVoiceClient_transcribe_uses_default_hrp_url() -> None:
    """api_url を省略したとき _DEFAULT_HRP_URL が setServerURL に渡されることを確認する。"""
    # Given
    mock_hrp = _make_mock_hrp()
    client = AmiVoiceClient(api_key="key")

    # When
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp):
        client.transcribe(b"audio-data")

    # Then
    mock_hrp.setServerURL.assert_called_once_with(_DEFAULT_HRP_URL)


def test_AmiVoiceClient_transcribe_uses_custom_api_url() -> None:
    """transcribe(api_url=...) でカスタム URL が使われることを確認する。"""
    # Given
    mock_hrp = _make_mock_hrp()
    custom = "https://custom.example.com/recognize"
    client = AmiVoiceClient(api_key="key")

    # When
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp):
        client.transcribe(b"audio-data", api_url=custom)

    # Then
    mock_hrp.setServerURL.assert_called_once_with(custom)


def test_AmiVoiceClient_transcribe_uses_constructor_http_api_url() -> None:
    """コンストラクタで http_api_url を指定したとき transcribe がそれを使うことを確認する。"""
    # Given: http_api_url をコンストラクタで指定したクライアント
    mock_hrp = _make_mock_hrp()
    custom = "https://constructor.example.com/recognize"
    client = AmiVoiceClient(api_key="key", http_api_url=custom)

    # When: api_url を省略して transcribe する
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp):
        client.transcribe(b"audio-data")

    # Then: コンストラクタの http_api_url が使われる
    mock_hrp.setServerURL.assert_called_once_with(custom)


def test_AmiVoiceClient_transcribe_recognition_timeout_passed_to_setter() -> None:
    """recognition_timeout が setRecognitionTimeout に文字列で渡されることを確認する。"""
    # Given
    mock_hrp = _make_mock_hrp()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, recognition_timeout=30000)

    # When
    client.transcribe(b"audio-data")

    # Then
    mock_hrp.setRecognitionTimeout.assert_called_once_with("30000")


def test_AmiVoiceClient_transcribe_segmenter_valid_passes_generated_parameter() -> None:
    """型付き segmenter 設定が HRP の setter に渡されることを確認する。"""
    # Given: 型付きセグメンター設定と注入済み HRP トランスポート
    mock_hrp = _make_mock_hrp()
    client = AmiVoiceClient(
        api_key="key",
        hrp_transport=mock_hrp,
        segmenter=SegmenterProperties(speaker_diarization=True, diarizer_alpha=1e-20),
    )

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: 生成された segmenterProperties 文字列が setter に渡される
    mock_hrp.setSegmenterProperties.assert_called_once_with("useDiarizer=1 diarizerAlpha=1e-20")


def test_AmiVoiceClient_transcribe_raw_segmenter_properties_valid_passes_unchanged() -> None:
    """既存の生 segmenter_properties 文字列がそのまま HRP に渡ることを確認する。"""
    # Given: 生文字列を指定したクライアント
    mock_hrp = _make_mock_hrp()
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp, segmenter_properties="threshold=5000")

    # When: transcribe を実行する
    client.transcribe(b"audio-data")

    # Then: 生文字列が変更されず setter に渡される
    mock_hrp.setSegmenterProperties.assert_called_once_with("threshold=5000")


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
    mock_hrp = _make_mock_hrp()
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

    # Then: 呼び出し時引数が setter に渡される
    mock_hrp.setGrammarFileNames.assert_called_once_with("-a-medical")
    mock_hrp.setCodec.assert_called_once_with("8K")
    mock_hrp.setKeepFillerToken.assert_called_once_with("false")
    mock_hrp.setConnectTimeout.assert_called_once_with(3000)
    mock_hrp.setReceiveTimeout.assert_called_once_with(4000)
    mock_hrp.setExtension.assert_called_once_with("override-tag")


def test_AmiVoiceClient_transcribe_omitted_args_use_instance_defaults() -> None:
    """transcribe() で引数を省略した場合にインスタンス既定値が使われることを確認する。"""
    # Given: 既定値を保持したクライアントと注入済み HRP トランスポート
    mock_hrp = _make_mock_hrp()
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

    # Then: コンストラクタ既定値が setter に渡される
    mock_hrp.setGrammarFileNames.assert_called_once_with("-a-general")
    mock_hrp.setCodec.assert_called_once_with("16K")
    mock_hrp.setKeepFillerToken.assert_called_once_with("true")
    mock_hrp.setConnectTimeout.assert_called_once_with(1000)
    mock_hrp.setReceiveTimeout.assert_called_once_with(2000)
    mock_hrp.setExtension.assert_called_once_with("default-tag")


def test_AmiVoiceClient_transcribe_connect_fails_raises_connection_error() -> None:
    """実 transport で接続失敗のとき ConnectionFailedError が送出されることを確認する。"""
    # Given
    mock_hrp = _make_mock_hrp(connect_ok=False)
    client = AmiVoiceClient(api_key="key")

    # When / Then
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp), pytest.raises(ConnectionFailedError):
        client.transcribe(b"audio-data")


def test_AmiVoiceClient_transcribe_server_error_raises_recognition_error() -> None:
    """サーバーエラーレスポンスのとき RecognitionError が送出されることを確認する。"""
    # Given
    mock_hrp = _make_mock_hrp('\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}')
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When / Then
    with pytest.raises(RecognitionError, match="bad request") as exc_info:
        client.transcribe(b"audio-data")

    assert exc_info.value.result is not None
    assert exc_info.value.result.is_error is True


def test_AmiVoiceClient_transcribe_raise_on_error_false_returns_error_result() -> None:
    """raise_on_error=False のときエラー結果が例外なく返ることを確認する。"""
    # Given
    mock_hrp = _make_mock_hrp('\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}')
    client = AmiVoiceClient(api_key="key", hrp_transport=mock_hrp)

    # When
    result = client.transcribe(b"audio-data", raise_on_error=False)

    # Then
    assert result.is_error is True
    assert result.data == {"code": "E001", "message": "bad request"}


def test_AmiVoiceClient_transcribe_disconnect_called_on_error() -> None:
    """FeedDataResume 失敗後も disconnect が呼ばれることを確認する（リソースリークなし）。"""
    # Given: feedDataResume が失敗するモック
    mock_hrp = MagicMock()
    mock_hrp.connect.return_value = True
    mock_hrp.feedDataResume.return_value = False
    mock_hrp.getLastMessage.return_value = "resume failed"

    client = AmiVoiceClient(api_key="key")

    # When
    with patch("amivoice.client._construct_hrp_transport", return_value=mock_hrp), pytest.raises(RecognitionError):
        client.transcribe(b"audio-data")

    # Then
    mock_hrp.disconnect.assert_called_once()


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
        return _make_mock_hrp(f'{{"text": "result-{call_count}"}}')

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


def test_AmiVoiceClient_stream_context_manager_returns_stream_session() -> None:
    """With client.stream() as session: で StreamSession が返ることを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = _make_mock_wrp()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When / Then: with ブロック内で StreamSession が取得できる
    with client.stream() as session:
        assert isinstance(session, StreamSession)


def test_AmiVoiceClient_stream_write_and_end_sends_audio() -> None:
    """session.write() でデータが feedData に渡されることを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = _make_mock_wrp()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: session.write() でチャンクを送信し、end() で終了する
    with client.stream() as session:
        session.write(b"chunk1")
        session.end()

    # Then: feedData に正しい引数で呼び出されている
    mock_wrp.feedData.assert_called_once_with(b"chunk1", 0, 6)


def test_AmiVoiceClient_stream_poll_yields_events() -> None:
    """session.poll() がストリーミングイベントを yield することを確認する。"""
    # Given: 1件の結果を返すモック WRP トランスポート
    mock_wrp = _make_mock_wrp(['{"text": "hello"}'])
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
    mock_wrp = _make_mock_wrp(['{"text": "part1"}', '{"text": "part2"}'])
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
    mock_wrp = _make_mock_wrp()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: with ブロックを正常終了する
    with client.stream() as session:
        session.end()

    # Then: disconnect が1回呼ばれている（リソースリークなし）
    mock_wrp.disconnect.assert_called_once()


def test_AmiVoiceClient_stream_uses_default_wrp_url() -> None:
    """api_url を省略したとき _DEFAULT_WRP_URL が使われることを確認する。"""
    # Given: wrp_transport を注入しない AmiVoiceClient（実 transport ファクトリをモック）
    mock_wrp = _make_mock_wrp()
    client = AmiVoiceClient(api_key="key")

    # When: api_url を省略して stream() を開く
    with patch("amivoice._stream._build_wrp_transport", return_value=mock_wrp) as mock_build, client.stream() as session:
        session.end()

    # Then: ファクトリの第2引数（api_url）に _DEFAULT_WRP_URL が渡されている
    _, _kwargs = mock_build.call_args
    # 第1引数は api_key、第2引数は api_url
    positional = mock_build.call_args.args
    assert positional[1] == _DEFAULT_WRP_URL


def test_AmiVoiceClient_stream_uses_custom_api_url() -> None:
    """stream(api_url=...) でカスタム URL が使われることを確認する。"""
    # Given: カスタム WRP エンドポイント URL
    mock_wrp = _make_mock_wrp()
    custom = "wss://custom.example.com/v1/"
    client = AmiVoiceClient(api_key="key")

    # When: カスタム URL を渡して stream() を開く
    with (
        patch("amivoice._stream._build_wrp_transport", return_value=mock_wrp) as mock_build,
        client.stream(api_url=custom) as session,
    ):
        session.end()

    # Then: ファクトリの第2引数にカスタム URL が渡されている
    positional = mock_build.call_args.args
    assert positional[1] == custom


def test_AmiVoiceClient_stream_uses_constructor_ws_api_url() -> None:
    """コンストラクタで ws_api_url を指定したとき stream がそれを使うことを確認する。"""
    # Given: ws_api_url をコンストラクタで指定したクライアント
    mock_wrp = _make_mock_wrp()
    custom = "wss://constructor.example.com/v1/"
    client = AmiVoiceClient(api_key="key", ws_api_url=custom)

    # When: api_url を省略して stream() を開く
    with (
        patch("amivoice._stream._build_wrp_transport", return_value=mock_wrp) as mock_build,
        client.stream() as session,
    ):
        session.end()

    # Then: コンストラクタの ws_api_url が第2引数に渡される
    assert mock_build.call_args.args[1] == custom


def test_AmiVoiceClient_stream_segmenter_valid_passes_generated_parameter() -> None:
    """型付き segmenter 設定が WRP の setter に渡されることを確認する。"""
    # Given: 型付き設定を指定したクライアント
    mock_wrp = _make_mock_wrp()
    client = AmiVoiceClient(api_key="key")
    properties = SegmenterProperties(languages=("ja", "en"))

    # When: 型付き設定で stream を開く
    with patch("amivoice._stream._Wrp.construct", return_value=mock_wrp), client.stream(segmenter=properties) as session:
        session.end()

    # Then: 生成された文字列が WRP の setter に渡される
    mock_wrp.setSegmenterProperties.assert_called_once_with("useLid=ja,en")


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
    mock_wrp = _make_mock_wrp()
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
        patch("amivoice._stream._build_wrp_transport", return_value=mock_wrp) as mock_build,
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
    params = mock_build.call_args.args[2]
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
    mock_wrp = _make_mock_wrp()
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
    with patch("amivoice._stream._build_wrp_transport", return_value=mock_wrp) as mock_build, client.stream() as session:
        session.end()

    # Then: コンストラクタ既定値が RecognitionParams として WRP transport builder に渡される
    params = mock_build.call_args.args[2]
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
        patch("amivoice._stream._build_wrp_transport", side_effect=ConnectionFailedError("connect failed")),
        pytest.raises(ConnectionFailedError),
        client.stream(),
    ):
        pass


def test_AmiVoiceClient_stream_resume_failed_disconnect_called() -> None:
    """FeedDataResume 失敗時に disconnect が呼ばれ RecognitionError が送出されることを確認する。"""
    # Given: feedDataResume が失敗するモック WRP トランスポート
    mock_wrp = MagicMock()
    mock_wrp.feedDataResume.return_value = False
    mock_wrp.getLastMessage.return_value = "resume failed"
    client = AmiVoiceClient(api_key="key")

    # When / Then: stream() の with ブロック入口で RecognitionError が送出され disconnect が呼ばれる
    with (
        patch("amivoice._stream._build_wrp_transport", return_value=mock_wrp),
        pytest.raises(RecognitionError, match="resume failed"),
        client.stream(),
    ):
        pass

    mock_wrp.disconnect.assert_called_once()


def test_AmiVoiceClient_stream_listener_set_before_feed_data_resume() -> None:
    """SetListener が feedDataResume より前に呼ばれることを確認する。"""
    # Given: 呼び出し順を記録するモック WRP トランスポート
    call_order: list[str] = []
    mock_wrp = MagicMock()
    mock_wrp.feedDataResume.return_value = True
    mock_wrp.getWaitingResults.return_value = 0
    mock_wrp.setListener.side_effect = lambda _: call_order.append("setListener")
    mock_wrp.feedDataResume.side_effect = lambda: call_order.append("feedDataResume") or True
    client = AmiVoiceClient(api_key="key")

    # When: with ブロックでセッションを開く
    with patch("amivoice._stream._build_wrp_transport", return_value=mock_wrp), client.stream():
        pass

    # Then: setListener が feedDataResume より先に呼ばれている
    assert call_order.index("setListener") < call_order.index("feedDataResume")


def test_AmiVoiceClient_stream_write_after_end_raises_recognition_error() -> None:
    """end() 後に write() を呼ぶと RecognitionError が送出されることを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = _make_mock_wrp()
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When / Then: end() 後の write() は RecognitionError を送出する
    with client.stream() as session:
        session.end()
        with pytest.raises(RecognitionError, match="ended"):
            session.write(b"too late")


def test_AmiVoiceClient_stream_enter_escape_hatch_works() -> None:
    """StreamConnectionManager.enter escape hatch が __enter__ と同等に動くことを確認する。"""
    # Given: モック WRP トランスポートを注入した AmiVoiceClient
    mock_wrp = _make_mock_wrp()
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
    mock_wrp.disconnect.assert_called_once()


def test_AmiVoiceClient_stream_events_blocking_yields_until_end() -> None:
    """session.events() が end() の終端マーカーまでブロッキングでイベントを yield することを確認する。"""
    # Given: 2件の結果を返すモック WRP トランスポート
    mock_wrp = _make_mock_wrp(['{"text": "part1"}', '{"text": "part2"}'])
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: end() 後に events() を消費する
    with client.stream() as session:
        session.end()
        events = list(session.events())

    # Then: partial/final を含む全イベントが順序どおりに返り、final が2件
    final_events = [e for e in events if e.is_final]
    assert [e.text for e in final_events] == ["part1", "part2"]
    assert all(e.type == "final" for e in final_events)


def test_AmiVoiceClient_stream_partial_event_type() -> None:
    """ResultUpdated が type="partial" の StreamEvent になることを確認する。"""
    # Given: feedDataPause で resultUpdated → resultFinalized を送るモック WRP
    mock_wrp = MagicMock()
    mock_wrp.connect.return_value = True
    mock_wrp.feedDataResume.return_value = True
    mock_wrp.feedData.return_value = True
    mock_wrp.getWaitingResults.return_value = 0

    def set_listener(listener: object) -> None:
        mock_wrp._listener = listener

    def emit() -> bool:
        mock_wrp._listener.resultUpdated("こんに")
        mock_wrp._listener.resultFinalized('{"text": "こんにちは"}')
        return True

    mock_wrp.setListener.side_effect = set_listener
    mock_wrp.feedDataPause.side_effect = emit
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: end() 後にイベントを収集する
    with client.stream() as session:
        session.end()
        events = list(session.events())

    # Then: 先頭が partial（途中結果）、末尾が final
    assert events[0].type == "partial"
    assert events[0].text == "こんに"
    assert events[0].is_partial is True
    assert events[-1].type == "final"


def test_AmiVoiceClient_stream_utterance_and_notification_events_delivered() -> None:
    """発話境界・サービス通知イベントが StreamEvent として届くことを確認する。"""
    # Given: 各種コールバックを発火するモック WRP
    mock_wrp = MagicMock()
    mock_wrp.connect.return_value = True
    mock_wrp.feedDataResume.return_value = True
    mock_wrp.feedData.return_value = True
    mock_wrp.getWaitingResults.return_value = 0

    def set_listener(listener: object) -> None:
        mock_wrp._listener = listener

    def emit() -> bool:
        mock_wrp._listener.utteranceStarted(100)
        mock_wrp._listener.utteranceEnded(500)
        mock_wrp._listener.eventNotified("E001", "ready")
        return True

    mock_wrp.setListener.side_effect = set_listener
    mock_wrp.feedDataPause.side_effect = emit
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When: end() 後にイベントを収集する
    with client.stream() as session:
        session.end()
        events = list(session.events())

    # Then: 発話開始・終了・通知イベントがそれぞれ届く
    by_type = {e.type: e for e in events}
    assert by_type["utterance_started"].utterance is not None
    assert by_type["utterance_started"].utterance.time == 100
    assert by_type["utterance_ended"].utterance.time == 500
    assert by_type["notification"].notification is not None
    assert by_type["notification"].notification.event_id == "E001"


def test_AmiVoiceClient_stream_events_timeout_raises() -> None:
    """events(timeout=...) でイベントが届かない場合に RecognitionError が送出されることを確認する。"""
    # Given: 結果を一切返さないモック WRP（end() 前は終端マーカーも来ない）
    mock_wrp = MagicMock()
    mock_wrp.connect.return_value = True
    mock_wrp.feedDataResume.return_value = True
    mock_wrp.feedDataPause.return_value = True
    mock_wrp.feedData.return_value = True
    mock_wrp.getWaitingResults.return_value = 0

    def set_listener(listener: object) -> None:
        mock_wrp._listener = listener

    mock_wrp.setListener.side_effect = set_listener
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When / Then: end() を呼ぶ前に events(timeout=...) を消費するとタイムアウトする
    with client.stream() as session:
        with pytest.raises(RecognitionError, match="Timed out waiting for stream event"):
            next(session.events(timeout=0.05))
        session.end()


def test_AmiVoiceClient_stream_end_timeout_raises_when_results_pending() -> None:
    """end(timeout=...) で待機結果が残り続ける場合に RecognitionError が送出されることを確認する。"""
    # Given: getWaitingResults が常に 1 を返し続けるモック WRP
    mock_wrp = MagicMock()
    mock_wrp.connect.return_value = True
    mock_wrp.feedDataResume.return_value = True
    mock_wrp.feedDataPause.return_value = True
    mock_wrp.getWaitingResults.return_value = 1

    def set_listener(listener: object) -> None:
        mock_wrp._listener = listener

    mock_wrp.setListener.side_effect = set_listener
    client = AmiVoiceClient(api_key="key", wrp_transport=mock_wrp)

    # When / Then: end(timeout=...) が待機結果ゼロを見ないままタイムアウトする
    with client.stream() as session, pytest.raises(RecognitionError, match="Timed out waiting for remaining"):
        session.end(timeout=0.2)
