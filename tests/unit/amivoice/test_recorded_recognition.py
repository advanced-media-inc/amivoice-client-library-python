"""匿名化した実API応答の回帰テスト、認識内容や時刻の将来の一致は保証しない"""

import json

import pytest

from amivoice import AmiVoiceClient, SentimentAnalysisClient
from amivoice.exceptions import RecognitionError

from .test_amivoice_client import HttpFake, WebSocketFake
from .test_api_key import FakeApiKeyIssuanceTransport


@pytest.mark.parametrize("name", ["success", "speech_rejected", "decoding_cancelled"])
def test_transcribe_recorded_response_valid_return_body_status(recorded_responses: dict[str, object], name: str) -> None:
    """HTTP200の実応答について本文のcodeとmessageで成否を判定する"""
    # Given: 認識成功、無音拒否、処理時間超過の実応答を返す通信処理
    body = recorded_responses["http"][name]
    fake = HttpFake(body)
    client = AmiVoiceClient(api_key="dummy", grammar_file_names="-a-general", hrp_transport=fake)
    # When: エラーも結果として読み取る
    result = client.transcribe(b"audio", raise_on_error=False)
    # Then: 200だけで成功扱いせず、単語や区間の情報を保持する
    assert result.data == body
    assert result.is_error == (name != "success")
    assert len(result.results) == len(body["results"])
    assert result.utterance_id is None


@pytest.mark.parametrize("name", ["speech_rejected", "decoding_cancelled"])
def test_transcribe_recorded_rejection_invalid_raise_RecognitionError(recorded_responses: dict[str, object], name: str) -> None:
    """拒否結果を例外に添付し、code oも成功にしない"""
    # Given: 実APIで取得した拒否結果
    body = recorded_responses["http"][name]
    client = AmiVoiceClient(api_key="dummy", grammar_file_names="-a-general", hrp_transport=HttpFake(body))
    # When: 既定のエラー処理で呼び出す
    with pytest.raises(RecognitionError) as caught:
        client.transcribe(b"audio")
    # Then: 成否の詳細と元の結果を保持する
    assert str(caught.value) == body["message"]
    assert caught.value.result.data == body
    assert caught.value.result.is_error


@pytest.mark.parametrize("kind", ["A", "R"])
def test_stream_recorded_rejection_then_success_valid_return_both_results(
    recorded_responses: dict[str, object], kind: str
) -> None:
    """先行区間の拒否で後続結果を失わない、Rは承認済みの互換動作として確認する"""
    # Given: 実際にAで受信した2区間を、AとRの両方で再現する
    bodies = recorded_responses["websocket"]["rejected_then_successful"]
    fake = WebSocketFake([kind + " " + json.dumps(body) for body in bodies])
    client = AmiVoiceClient(api_key="dummy", grammar_file_names="-a-general", codec="16K", wrp_transport=fake)
    # When: 終了応答まで待機する
    with client.stream() as session:
        session.write(b"audio")
        session.end(timeout=1)
        results = session.results()
        events = list(session.poll())
    # Then: 拒否と成功を独立に保持する、Rを実測したとは扱わない
    assert [result.is_error for result in results] == [True, False]
    assert [result.data for result in results] == bodies
    assert [event.type for event in events] == ["final", "final"]
    assert results[0].data["code"] == "o"
    assert results[1].text == "豊かな未来を創造していくことを目指します。"


def test_list_parameters_recorded_response_valid_return_all_definitions(recorded_responses: dict[str, object]) -> None:
    """実応答の20定義を読み取り、負の最小値を誤って拒否しない"""
    # Given: 公開定義だけを含む実JSON応答
    body = recorded_responses["sentiment_parameters"]
    transport = FakeApiKeyIssuanceTransport(responses=[(200, json.dumps(body).encode())])
    client = SentimentAnalysisClient(api_key="dummy", transport=transport)
    # When: 感情パラメータの定義を取得する
    definitions = client.list_parameters()
    # Then: 全件を読み取り、実応答の境界値を保持する
    assert len(definitions) == 20
    atmosphere = next(definition for definition in definitions if definition.name == "atmosphere")
    assert (atmosphere.minimum, atmosphere.maximum) == (-100.0, 100.0)
    assert all(definition.minimum <= definition.maximum for definition in definitions)
