"""実応答をローカルサーバーで再生し、公開APIから送受信を検証する"""

import json

import pytest

from amivoice import AmiVoiceClient
from amivoice.exceptions import RecognitionError

from .recognition_mock_servers import RecordedHttpServer, RecordedWebSocketServer
from .recognition_mock_servers import parse_recognition_multipart as _multipart_parts


@pytest.mark.parametrize("name", ["success", "speech_rejected", "decoding_cancelled"])
def test_transcribe_local_chunked_recording_valid_return_full_response(recorded_responses: dict[str, object], name: str) -> None:
    """本物のHTTP通信で、分割されたUTF-8とHTTP200の失敗を処理する"""
    # Given: 実APIの匿名化した本文をチャンク転送するloopbackサーバー
    body = recorded_responses["http"][name]
    audio = b"\x00\xff\r\nwave-data"
    with RecordedHttpServer(json.dumps(body, ensure_ascii=False).encode()) as server:
        client = AmiVoiceClient(
            api_key="dummy",
            grammar_file_names="-a-general",
            codec="LSB16K",
            http_api_url=server.url,
            connect_timeout=1000,
            receive_timeout=2000,
        )
        # When: モック通信処理を注入せず、公開APIで認識する
        result = client.transcribe(audio, profile_words="テスト とりぷるだぶりゅー", raise_on_error=False)
    # Then: チャンクを正しく結合し、成功判定と認証情報の置き場所を守る
    assert result.data == body
    assert result.is_error == bool(body["code"])
    path, headers, sent = server.received[0]
    assert path == "/v1/recognize"
    assert headers["Authorization"] == "Bearer dummy"
    parts = _multipart_parts(headers["Content-Type"], sent)
    assert [name for name, _ in parts] == ["d", "c", "a"]
    assert parts[-1] == ("a", audio)
    assert b"dummy" not in sent
    assert b"profileWords=%E3%83%86%E3%82%B9%E3%83%88%20" in dict(parts)["d"]


@pytest.mark.parametrize("name", ["speech_rejected", "decoding_cancelled"])
def test_transcribe_local_http_200_rejection_invalid_raise_RecognitionError(
    recorded_responses: dict[str, object], name: str
) -> None:
    """200の認識失敗をソケット通信経由でも例外にする"""
    # Given: HTTPステータスは200で、本文が認識失敗のサーバー
    body = recorded_responses["http"][name]
    with RecordedHttpServer(json.dumps(body).encode()) as server:
        client = AmiVoiceClient(api_key="dummy", grammar_file_names="-a-general", http_api_url=server.url, receive_timeout=2000)
        # When / Then: 本文の失敗を検出し、その結果を添付する
        with pytest.raises(RecognitionError) as caught:
            client.transcribe(b"audio")
        assert caught.value.result.data == body
        assert str(caught.value) == body["message"]


@pytest.mark.parametrize("fragment_final", [False, True])
def test_stream_local_recorded_labels_valid_return_events_and_masked_audio(
    recorded_responses: dict[str, object], fragment_final: bool
) -> None:
    """実際のイベント列と日本語の分割フレームを、公開API経由で処理する"""
    # Given: s/S/E/C/U/A/eを再現し、必要に応じてUTF-8を分割するサーバー
    packets = recorded_responses["websocket"]["labelled"]
    with RecordedWebSocketServer(packets, fragment_final=fragment_final) as server:
        client = AmiVoiceClient(
            api_key="dummy",
            grammar_file_names="-a-general",
            codec="16K",
            ws_api_url=server.url,
            segmenter_properties="useDiarizer=1 useLid=ja",
            profile_words="テスト とりぷるだぶりゅー",
            connect_timeout=1000,
            receive_timeout=2000,
        )
        # When: マスクした音声を送り、最終結果と終了応答を待つ
        with client.stream() as session:
            session.write(b"\x00\xff")
            session.write(b"x" * 200)
            session.end(timeout=2)
            events = list(session.poll())
            result = session.results()[0]
    # Then: 発話終了時刻と認識区間の終了時刻は別物として保持する
    assert [event.type for event in events] == [
        "utterance_started",
        "utterance_ended",
        "notification",
        "partial",
        "partial",
        "partial",
        "final",
    ]
    assert events[0].utterance.time == 500
    assert events[1].utterance.time == 2100
    assert result.results[0].endtime == 2084
    assert result.text == "テスト"
    token = result.results[0].tokens[0]
    assert (token.label, token.language, token.spoken) == ("speaker0", "ja", "とりぷるだぶりゅー")
    assert server.frames[1:] == [(2, b"p\x00\xff"), (2, b"p" + b"x" * 200), (1, b"e")]
    assert b"Authorization: Bearer dummy\r\n" in server.upgrade_request
    assert b"dummy" not in server.frames[0][1]
    assert server.pongs == ([b"probe"] if fragment_final else [])
    assert not session._thread.is_alive()


def test_stream_local_updates_disabled_valid_return_no_partial(recorded_responses: dict[str, object]) -> None:
    """resultUpdatedInterval=0の実測列を再生して最終結果だけを取得する"""
    # Given: Uのない実際のイベント列
    packets = recorded_responses["websocket"]["updates_disabled"]
    with RecordedWebSocketServer(packets) as server:
        client = AmiVoiceClient(
            api_key="dummy",
            grammar_file_names="-a-general",
            codec="16K",
            ws_api_url=server.url,
            result_updated_interval=0,
            receive_timeout=2000,
        )
        # When: 音声送信と終了待機を行う
        with client.stream() as session:
            session.write(b"audio")
            session.end(timeout=2)
            events = list(session.poll())
    # Then: 最終結果を失わず、設定値0をコマンドから欠落させない
    assert not any(event.is_partial for event in events)
    assert [event.result.text for event in events if event.is_final] == ["トリプルW"]
    assert b"resultUpdatedInterval=0" in server.frames[0][1]


def test_stream_local_no_input_error_invalid_raise_RecognitionError(recorded_responses: dict[str, object]) -> None:
    """実際の無入力タイムアウト応答を黙って正常終了にしない"""
    # Given: 実測したeのエラーメッセージ、時間の経過自体はモックで検証しない
    error_packet = recorded_responses["websocket"]["no_input_timeout"][-1]
    with RecordedWebSocketServer([], end_error=error_packet) as server:
        client = AmiVoiceClient(
            api_key="dummy",
            grammar_file_names="-a-general",
            codec="LSB16K",
            ws_api_url=server.url,
            no_input_timeout=200,
            receive_timeout=2000,
        )
        # When / Then: 終了待機で実際のメッセージを含む例外を通知する
        with pytest.raises(RecognitionError, match="e no input timeout occurred"), client.stream() as session:
            session.write(b"\x00\x00")
            session.end(timeout=2)
    assert b"noInputTimeout=200" in server.frames[0][1]
    assert not session._thread.is_alive()
