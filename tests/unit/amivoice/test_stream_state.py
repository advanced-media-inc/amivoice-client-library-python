"""WRP セッションの期限、エラー伝播、終了状態のテスト"""

import pytest

from amivoice import AmiVoiceClient
from amivoice.exceptions import RecognitionError

from ._recognition_fakes import make_websocket_transport


@pytest.mark.parametrize("recognition_started", [False, True])
def test_stream_start_missing_ack_invalid_raise_RecognitionError(recognition_started: bool) -> None:
    """C の有無にかかわらず s 確認応答だけで開始を判定する"""
    # Given: 受信自体は無期限にブロックする接続
    transport = make_websocket_transport()
    transport.send_text.side_effect = None
    if recognition_started:
        transport._messages.put("C")
    client = AmiVoiceClient(api_key="test", receive_timeout=10, wrp_transport=transport)
    # When / Then: 開始確認のタイムアウトで接続を閉じる
    with pytest.raises(RecognitionError, match="start acknowledgement"), client.stream():
        pass
    transport.close.assert_called_once()


def test_stream_end_missing_ack_invalid_raise_RecognitionError() -> None:
    """未確定結果がなくても終了確認の期限を守る"""
    # Given: e 確認だけを返さない接続
    transport = make_websocket_transport()
    original = transport.send_text.side_effect
    transport.send_text.side_effect = lambda message: original(message) if message != "e" else None
    client = AmiVoiceClient(api_key="test", wrp_transport=transport)
    # When / Then: end と events の両方に同じ失敗が届く
    with client.stream() as session:
        with pytest.raises(RecognitionError, match="end acknowledgement"):
            session.end(timeout=0.01)
        with pytest.raises(RecognitionError, match="end acknowledgement"):
            list(session.events())
        with pytest.raises(RecognitionError):
            session.end()
    assert not session._receiver.is_alive()


@pytest.mark.parametrize("operation", ["poll", "events", "end", "write"])
def test_stream_receiver_error_invalid_raise_RecognitionError(operation: str) -> None:
    """受信スレッドの失敗がすべての利用経路へ伝播する"""
    # Given: 開始後に接続が切れる
    transport = make_websocket_transport()
    client = AmiVoiceClient(api_key="test", wrp_transport=transport)
    with client.stream() as session:
        transport._messages.put(RecognitionError("receiver failed"))
        with session._condition:
            assert session._condition.wait_for(lambda: session._error is not None, timeout=1)
        # When / Then: エラーを bool や無限待機にせず送出する
        with pytest.raises(RecognitionError, match="receiver failed"):
            if operation in {"poll", "events"}:
                list(getattr(session, operation)())
            elif operation == "write":
                session.write(b"audio")
            else:
                session.end()
    assert not session._receiver.is_alive()


def test_stream_end_repeated_valid_return_once() -> None:
    """End は冪等で、消費した終端も再度ブロックしない"""
    # Given: 正常に認識する接続
    transport = make_websocket_transport()
    client = AmiVoiceClient(api_key="test", wrp_transport=transport)
    # When: end とイベント消費を繰り返す
    with client.stream() as session:
        session.end()
        session.end()
        assert len(list(session.poll())) == 2
        assert list(session.events()) == []
    # Then: 終了コマンドは一回だけ
    assert [call.args[0] for call in transport.send_text.call_args_list].count("e") == 1


def test_stream_context_without_end_valid_close_receiver() -> None:
    """End を省略してもコンテキスト終了で受信待機を解除する"""
    # Given: 結果を返さない接続
    transport = make_websocket_transport(results=[])
    client = AmiVoiceClient(api_key="test", wrp_transport=transport)
    # When: end せずコンテキストを抜ける
    with client.stream() as session:
        pass
    # Then: スレッドとイベントストリームを閉じる
    assert not session._receiver.is_alive()
    assert list(session.events()) == []
    with pytest.raises(RecognitionError, match="ended"):
        session.write(b"audio")


def test_stream_send_error_invalid_raise_RecognitionError() -> None:
    """送信失敗もイベント消費者へ伝播する"""
    # Given: 音声送信だけに失敗する接続
    transport = make_websocket_transport()
    transport.send_binary.side_effect = RecognitionError("send failed")
    client = AmiVoiceClient(api_key="test", wrp_transport=transport)
    # When / Then: 送信とイベントで同じエラーが届く
    with client.stream() as session:
        with pytest.raises(RecognitionError, match="send failed"):
            session.write(b"audio")
        with pytest.raises(RecognitionError, match="send failed"):
            list(session.events())
