"""認識クライアントの入力境界を記録するテスト用トランスポート"""

import queue
from unittest.mock import MagicMock

from amivoice._http_recognition import HttpRecognitionTransport
from amivoice._params import RecognitionParams
from amivoice._recognition_protocol import recognition_wire_values
from amivoice._websocket_transport import WebSocketTransport
from amivoice.exceptions import ConnectionFailedError, RecognitionError
from amivoice.models import RecognitionResult, parse_result


def make_http_transport(result_json: str = '{"text": "hello"}', *, connect_ok: bool = True) -> MagicMock:
    """HTTP 認識入力を記録しサービス応答を返すモックを生成する"""
    transport = MagicMock(spec=HttpRecognitionTransport)

    def transcribe(
        api_url: str, api_key: str, params: RecognitionParams, audio: bytes, *, raise_on_error: bool = True
    ) -> RecognitionResult:
        """受け取った入力に応じて例外または結果を返す"""
        if not connect_ok:
            raise ConnectionFailedError("connection failed")
        return parse_result(result_json, raise_on_error=raise_on_error)

    transport.transcribe.side_effect = transcribe
    return transport


def http_wire_values(transport: MagicMock) -> dict[str, object]:
    """HTTP 境界に渡った設定を電文値として検査する"""
    params = transport.transcribe.call_args.args[2]
    return {
        **recognition_wire_values(params),
        "codec": params.codec,
        "connectTimeout": params.connect_timeout,
        "receiveTimeout": params.receive_timeout,
    }


def make_websocket_transport(results: list[str] | None = None, *, connect_ok: bool = True) -> MagicMock:
    """確認応答と認識結果をキューへ流す接続済み WebSocket モックを作る"""
    transport = MagicMock(spec=WebSocketTransport)
    transport._messages = queue.SimpleQueue()
    if results is None:
        results = ['{"text": "stream result"}']
    if not connect_ok:
        transport.connect.side_effect = ConnectionFailedError("connection failed")

    def send_text(command: str) -> None:
        """WRP 電文に応じてサーバー応答をキューへ投入する"""
        if command.startswith("s "):
            transport._messages.put("s")
        elif command == "e":
            for raw in results:
                transport._messages.put("S 0")
                transport._messages.put("A " + raw)
            transport._messages.put("e")

    def receive_message() -> str:
        """サーバー応答または切断例外を返す"""
        item = transport._messages.get()
        if isinstance(item, Exception):
            raise item
        return item

    transport.send_text.side_effect = send_text
    transport.receive_message.side_effect = receive_message
    transport.close.side_effect = lambda: transport._messages.put(RecognitionError("closed"))
    return transport


def assert_wrp_parameter(transport: MagicMock, wire_name: str, expected: str) -> None:
    """開始コマンド内のパラメータと引用符エスケープを確認する"""
    if " " in expected or '"' in expected:
        expected = '"' + expected.replace('"', '""') + '"'
    command = transport.send_text.call_args_list[0].args[0]
    assert f" {wire_name}={expected}" in command


def assert_wrp_parameter_absent(transport: MagicMock, wire_name: str) -> None:
    """開始コマンドで未指定パラメータが送られないことを確認する"""
    command = transport.send_text.call_args_list[0].args[0]
    assert f" {wire_name}=" not in command
