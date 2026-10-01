"""認識クライアントの入力境界を記録するテスト用トランスポート"""

from unittest.mock import MagicMock

from amivoice._http_recognition import HttpRecognitionTransport
from amivoice._params import RecognitionParams
from amivoice._recognition_protocol import recognition_wire_values
from amivoice.exceptions import ConnectionFailedError
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
