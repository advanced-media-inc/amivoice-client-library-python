"""ストリーム送信と終了要求の順序・失敗時回収のテスト"""

import threading

import pytest

from amivoice import AmiVoiceClient, RecognitionSettings
from amivoice.exceptions import RecognitionError

from .test_amivoice_client import WebSocketFake


def test_stream_end_concurrent_write_valid_preserve_command_order() -> None:
    """送信中の音声より先にeを送らない"""
    # Given: 音声送信を途中で待機させる通信処理
    fake = WebSocketFake()
    sending = threading.Event()
    release = threading.Event()
    ending = threading.Event()
    end_sent = threading.Event()
    original_send_text = fake.send_text

    def delayed_audio(audio: bytes) -> None:
        sending.set()
        assert release.wait(2)
        fake.sent.append(audio)

    def tracked_text(text: str) -> None:
        if text == "e":
            end_sent.set()
        original_send_text(text)

    fake.send_audio = delayed_audio
    fake.send_text = tracked_text
    manager = AmiVoiceClient(
        api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general", codec="16K"), wrp_transport=fake
    ).stream()
    session = manager.enter()
    failures = []

    def finish() -> None:
        ending.set()
        try:
            session.end(timeout=1)
        except Exception as exc:
            failures.append(exc)

    writer = threading.Thread(target=session.write, args=(b"audio",))
    ender = threading.Thread(target=finish)
    writer.start()
    assert sending.wait(1)
    # When: 音声送信中に終了を要求する
    ender.start()
    assert ending.wait(1)
    try:
        assert not end_sent.wait(0.05)
    finally:
        release.set()
        writer.join(timeout=2)
        ender.join(timeout=2)
        manager.__exit__(RuntimeError, None, None)
    # Then: 音声の後に終了コマンドを送る
    assert not failures
    assert fake.sent[-2:] == [b"audio", "e"]


def test_stream_end_send_failure_invalid_close_session() -> None:
    """e送信失敗時も受信スレッドを残さない"""
    # Given: 開始後にe送信を失敗させる通信処理
    fake = WebSocketFake()
    original = fake.send_text

    def fail_end(text: str) -> None:
        if text == "e":
            raise RecognitionError("send failed")
        original(text)

    fake.send_text = fail_end
    manager = AmiVoiceClient(
        api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general", codec="16K"), wrp_transport=fake
    ).stream()
    session = manager.enter()
    # When / Then: 終了失敗は例外として通知し切断する
    try:
        with pytest.raises(RecognitionError):
            session.end(timeout=1)
        assert fake.closed
        assert not session._thread.is_alive()
    finally:
        manager.__exit__(RuntimeError, None, None)


def test_stream_q_and_g_events_valid_ignore_and_finish() -> None:
    """QとGイベントを無視し認識セッションを正常終了する"""
    # Given: 終了応答の前にQとGイベントを返す通信処理
    fake = WebSocketFake(events=["Q ignored", "G ignored"])
    manager = AmiVoiceClient(
        api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general", codec="16K"), wrp_transport=fake
    ).stream()

    # When: セッションを終了して到着済みイベントを取得する
    with manager as session:
        session.end(timeout=1)
        events = list(session.poll())

    # Then: QとGをイベントとして公開せず正常終了する
    assert events == []
    assert not session._thread.is_alive()
