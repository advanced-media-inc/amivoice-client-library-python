"""Java形式のsetterではなく公開API境界で認識動作を確認する"""

import inspect
import json
import queue
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from amivoice import AmiVoiceClient, Codec, Engine, ProfileWord, SegmenterProperties, transcribe
from amivoice._params import RecognitionParams
from amivoice.exceptions import AuthenticationError, ConfigurationError, RecognitionError


class HttpFake:
    """同期HTTPの送信内容を記録するテスト用通信処理"""

    def __init__(self, result: dict[str, object] | None = None, status: int = 200) -> None:
        """レスポンスを設定する"""
        self.result = result if result is not None else {"text": "hello", "code": "", "message": ""}
        self.status = status
        self.calls: list[tuple[str, dict[str, str], bytes, RecognitionParams]] = []

    def request(self, url: str, headers: dict[str, str], body: bytes, params: RecognitionParams) -> tuple[int, bytes]:
        """HTTP呼び出しを記録しJSONを返す"""
        self.calls.append((url, headers, body, params))
        return self.status, json.dumps(self.result).encode()


class WebSocketFake:
    """別スレッドにs/e応答とイベントを配信するテスト用接続"""

    def __init__(self, events: list[str] | None = None, start_response: str = "s", end_response: bool = True) -> None:
        """配信するイベントを保持する"""
        self.events = events or []
        self.start_response = start_response
        self.end_response = end_response
        self.packets: queue.Queue[str | None] = queue.Queue()
        self.sent: list[str | bytes] = []
        self.closed = False
        self.connection: tuple[str, str, RecognitionParams] | None = None

    def connect(self, url: str, api_key: str, params: RecognitionParams) -> None:
        """接続先と設定を記録する"""
        self.connection = (url, api_key, params)

    def send_text(self, text: str) -> None:
        """開始応答又は終了時のイベント列を配信する"""
        self.sent.append(text)
        if text.startswith("s "):
            self.packets.put(self.start_response)
        elif text == "e":
            for event in self.events:
                self.packets.put(event)
            if self.end_response:
                self.packets.put("e")

    def send_audio(self, audio: bytes) -> None:
        """音声の送信を記録する"""
        self.sent.append(audio)

    def receive_text(self) -> str | None:
        """別スレッドからの受信を模倣する"""
        return self.packets.get()

    def close(self) -> None:
        """受信スレッドを解除する"""
        self.closed = True
        self.packets.put(None)


def _client(**kwargs: object) -> AmiVoiceClient:
    return AmiVoiceClient(api_key="dummy", grammar_file_names=Engine.A_GENERAL, codec=Codec.HEADER_16K, **kwargs)


@pytest.mark.parametrize("target", [AmiVoiceClient, AmiVoiceClient.transcribe, AmiVoiceClient.stream, transcribe])
@pytest.mark.parametrize(
    "name",
    [
        "mode",
        "result_type",
        "voice_detection",
        "accept_topic",
        "content_type",
        "accept",
        "domain_id",
        "segmenter_type",
        "result_encoding",
    ],
)
def test_public_api_unsupported_argument_invalid_omit_signature(target: object, name: str) -> None:
    """未掲載の引数を公開APIから除去する"""
    # Given: 公開クライアントと便利関数
    # When: 公開シグネチャを取得する
    parameters = inspect.signature(target).parameters
    # Then: 未掲載設定は存在しない
    assert name not in parameters


def test_client_http_defaults_valid_return_result() -> None:
    """公式形式のレスポンスを返し認証はヘッダだけで送る"""
    # Given: 設定済みのクライアント
    fake = HttpFake()
    client = _client(hrp_transport=fake, logging_opt_out=True)
    # When: 同期認識する
    result = client.transcribe(b"audio")
    # Then: nolog接続先で認証情報を本文に含めない
    url, headers, body, _ = fake.calls[0]
    assert result.text == "hello"
    assert url == "https://acp-api.amivoice.com/v1/nolog/recognize"
    assert headers["Authorization"] == "Bearer dummy"
    assert b"dummy" not in body
    assert b'name="c"' not in body


def test_client_http_overrides_valid_return_independent_settings() -> None:
    """呼び出し時の上書きが次の呼び出しに残らない"""
    # Given: 既定の集計タグと認識時間
    fake = HttpFake()
    client = _client(hrp_transport=fake, billing_key="base", recognition_timeout=100)
    # When: 今回だけ別の時間を設定して次に既定で呼ぶ
    client.transcribe(
        b"a", recognition_timeout=0, billing_key="override", segmenter=SegmenterProperties(pre_time=200), selected_channel=(0, 2)
    )
    client.transcribe(b"b")
    # Then: 0も有効な上書き値であり独立している
    assert fake.calls[0][3].recognition_timeout == 0
    assert b"selectedChannel%3D0-2" in fake.calls[0][2]
    assert fake.calls[1][3].recognition_timeout == 100
    assert fake.calls[1][3].billing_key == "base"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"segmenter": SegmenterProperties(), "segmenter_properties": "threshold=1"},
        {"selected_channel": 1, "audio_filter_properties": "selectedChannel=0"},
        {"extension": "{}", "billing_key": "tag"},
        {"selected_channel": (1, 2)},
    ],
)
def test_client_conflicting_settings_invalid_raise_ConfigurationError(kwargs: dict[str, object]) -> None:
    """相互排他設定や公式にないチャネル範囲を拒否する"""
    # Given: 不正な設定
    # When / Then: 送信前に拒否する
    with pytest.raises(ConfigurationError):
        _client(**kwargs)


@pytest.mark.parametrize("code", ["o", "-", "!", "t"])
def test_client_http_error_200_invalid_raise_RecognitionError(code: str) -> None:
    """HTTP200でも本文で失敗を判定する"""
    # Given: エラー結果を200で返すサーバ
    fake = HttpFake({"text": "", "code": code, "message": "rejected"})
    client = _client(hrp_transport=fake)
    # When / Then: 例外を送出し、抑制時は失敗結果を返す
    with pytest.raises(RecognitionError, match="rejected"):
        client.transcribe(b"audio")
    assert client.transcribe(b"audio", raise_on_error=False).is_error


@pytest.mark.parametrize(
    "result", [{"text": "hello"}, {"code": "", "message": "", "text": ""}, {"code": 0, "message": "", "text": "x"}]
)
def test_client_http_malformed_response_invalid_raise_RecognitionError(result: dict[str, object]) -> None:
    """結果フィールドが不正な場合に成功扱いしない"""
    # Given: 不正なJSON構造
    client = _client(hrp_transport=HttpFake(result))
    # When / Then: 成功結果にはしない
    with pytest.raises(RecognitionError):
        client.transcribe(b"audio")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"http_api_url": None},
        {"ws_api_url": None},
        {"logging_opt_out": "false"},
        {"http_api_url": "https://host.test/v1/recognize?u=dummy"},
        {"http_api_url": "https://host.test/v1/recognize", "logging_opt_out": True},
    ],
)
def test_client_endpoint_configuration_invalid_raise_ConfigurationError(kwargs: dict[str, object]) -> None:
    """設定の取り違えによるログ保存やキーのURL混入を防ぐ"""
    # Given: 不正な接続設定
    # When / Then: 初期化時に拒否する
    with pytest.raises(ConfigurationError):
        _client(**kwargs)


def test_client_authentication_missing_invalid_raise_AuthenticationError(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数も引数もない場合は拒否する"""
    # Given: 認証情報のない環境
    monkeypatch.delenv("AMIVOICE_API_KEY", raising=False)
    # When / Then: クライアントを生成できない
    with pytest.raises(AuthenticationError):
        AmiVoiceClient()


def test_client_http_websocket_options_valid_omit_http_parameters() -> None:
    """共有設定のWebSocket専用値をHTTPに送らない"""
    # Given: 途中結果間隔と無入力タイムアウト
    fake = HttpFake()
    client = _client(hrp_transport=fake, result_updated_interval=1000, no_input_timeout=500)
    # When: 同期認識する
    client.transcribe(b"audio")
    # Then: 専用パラメータは生成しない
    assert b"resultUpdatedInterval" not in fake.calls[0][2]
    assert b"noInputTimeout" not in fake.calls[0][2]


def test_client_http_parallel_calls_valid_return_independent_results() -> None:
    """設定を複数スレッドの呼び出しで共有しても上書きを混ぜない"""
    # Given: 共通クライアント
    fake = HttpFake()
    client = _client(hrp_transport=fake)
    # When: 並列で呼ぶ
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda n: client.transcribe(b"a", recognition_timeout=n), range(8)))
    # Then: 各呼び出しに独立した設定がある
    assert len(results) == 8
    assert {call[3].recognition_timeout for call in fake.calls} == set(range(8))


def test_client_stream_event_sequence_valid_return_results_after_end() -> None:
    """e送信後のAとRを含めすべての認識結果を保持する"""
    # Given: 公式イベント列とA/R
    result = '{"text":"hello","code":"","message":""}'
    fake = WebSocketFake(["S 0", "C", 'U {"text":"hel..."}', "E 10", "A " + result, "R " + result, "G ignored"])
    client = _client(wrp_transport=fake, logging_opt_out=True)
    # When: 送信を終了しイベントを読む
    with client.stream() as session:
        session.write(b"audio")
        session.end(timeout=1)
        events = list(session.events(timeout=0.1))
        assert len(session.results()) == 2
        assert list(session.poll()) == []
        assert list(session.events(timeout=0.1)) == []
        with pytest.raises(RecognitionError, match="ended"):
            session.write(b"x")
    # Then: JSON途中結果、発話イベントとCを公開しGは無視する
    assert [e.type for e in events] == ["utterance_started", "notification", "partial", "utterance_ended", "final", "final"]
    assert events[2].text == "hel..."
    assert fake.connection[0] == "wss://acp-api.amivoice.com/v1/nolog/"
    assert "authorization=" not in fake.sent[0]
    assert fake.closed


@pytest.mark.parametrize(
    "response,exception",
    [("s can't verify service authorization", AuthenticationError), ("s received unsupported audio format", RecognitionError)],
)
def test_client_stream_start_error_invalid_raise_exception(response: str, exception: type[Exception]) -> None:
    """開始失敗時は例外としソケットを回収する"""
    # Given: 失敗する開始要求
    fake = WebSocketFake(start_response=response)
    # When / Then: 接続後のエラーも回収する
    with pytest.raises(exception), _client(wrp_transport=fake).stream():
        pass
    assert fake.closed


def test_client_stream_end_timeout_invalid_raise_RecognitionError() -> None:
    """終了応答がないとき結果数が0でもタイムアウトする"""
    # Given: e応答を返さないサーバ
    fake = WebSocketFake(end_response=False)
    manager = _client(wrp_transport=fake).stream()
    session = manager.enter()
    # When / Then: e応答を必ず待機して失敗を通知する
    try:
        with pytest.raises(RecognitionError, match="end response"):
            session.end(timeout=0.01)
        with pytest.raises(RecognitionError):
            list(session.events(timeout=0.1))
    finally:
        manager.__exit__(RuntimeError, None, None)
    assert fake.closed


def test_client_stream_invalid_event_invalid_raise_RecognitionError() -> None:
    """受信スレッド内の解析エラーを呼び出し元へ伝える"""
    # Given: 不正な発話時刻
    fake = WebSocketFake(["S not-a-time"])
    manager = _client(wrp_transport=fake).stream()
    session = manager.enter()
    # When / Then: 終了待機で受信エラーが通知される
    try:
        with pytest.raises(RecognitionError):
            session.end(timeout=1)
    finally:
        manager.__exit__(RuntimeError, None, None)


def test_client_stream_context_exception_invalid_close_transport() -> None:
    """利用者コードの例外を隠さず接続を閉じる"""
    # Given: 接続できるクライアント
    fake = WebSocketFake()
    # When / Then: 終了要求なしで切断し元の例外を保持する
    with pytest.raises(ValueError), _client(wrp_transport=fake).stream():
        raise ValueError("application error")
    assert fake.closed


def test_client_profile_words_sequence_valid_return_official_format() -> None:
    """型付き辞書を送信用の文字列へ変換する"""
    # Given: 単語オブジェクト列
    fake = HttpFake()
    client = _client(hrp_transport=fake)
    # When: 単語を渡す
    client.transcribe(b"a", profile_words=[ProfileWord("AMI", spoken="あみ")])
    # Then: 公式のスペース区切り形式になる
    assert fake.calls[0][3].profile_words == "AMI あみ"


def test_client_default_transport_valid_construct_per_call() -> None:
    """毎回HTTP接続を生成して共有しない"""
    # Given: 通信処理の生成だけをモック化
    fake = HttpFake()
    with patch("amivoice.client.HttpRecognitionConnection", return_value=fake) as factory:
        # When: 同じクライアントで2回認識する
        client = _client()
        client.transcribe(b"a")
        client.transcribe(b"b")
    # Then: 生成は呼び出しごとである
    assert factory.call_count == 2
