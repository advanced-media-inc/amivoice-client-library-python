"""非同期HTTPの構造化エラーと安全な表示を検証する"""

import json

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncHttpApiError, AuthenticationError, RecognitionSettings
from amivoice._async_models import parse_submission

from .test_async_client import RecordingTransport


@pytest.mark.parametrize("code", ["+", "o", "^"])
def test_parse_submission_rejection_valid_raise_structured_error(code: str) -> None:
    """受付拒否を本文の再解析なしで扱える"""
    # Given: HTTP200の受付拒否
    data = {"code": code, "message": "sensitive server detail", "text": "", "results": []}
    body = json.dumps(data).encode()
    # When: 受付拒否を捕捉する
    with pytest.raises(AsyncHttpApiError) as caught:
        parse_submission(body)
    # Then: 本文情報を属性で保持し例外の表示から分離する
    error = caught.value
    assert error.code == code
    assert error.api_message == data["message"]
    assert error.data == data and error.raw_body == body
    assert "sensitive" not in str(error)


@pytest.mark.parametrize("body", [b"not-json", b"\xff", b"[]", b'{"code":1,"message":false}'])
def test_parse_submission_malformed_invalid_raise_safe_error(body: bytes) -> None:
    """壊れた本文でも属性解析による例外を漏らさない"""
    # Given: 解析不能または型が不正な受付応答
    # When: 受付応答を解析する
    with pytest.raises(AsyncHttpApiError) as caught:
        parse_submission(body)
    # Then: 型を捏造せず元の本文を保持する
    assert caught.value.code is None and caught.value.api_message is None
    assert caught.value.raw_body == body


@pytest.mark.parametrize("operation", ["submit", "get_job"])
def test_request_authentication_invalid_raise_both_error_types(operation: str) -> None:
    """HTTP401は認証例外と非同期HTTP例外の両方で捕捉できる"""
    # Given: 認証失敗のHTTP応答
    transport = RecordingTransport([(401, b"Failed to authorize for the API key")])
    client = AmiVoiceAsyncClient(
        settings=RecognitionSettings(grammar_file_names="-a-general"), api_key="dummy", transport=transport
    )
    # When: 認証が必要な操作を行う
    with pytest.raises(AuthenticationError) as caught:
        getattr(client, operation)(b"audio" if operation == "submit" else "job1")
    # Then: 既存の捕捉方法とHTTP詳細を維持する
    assert isinstance(caught.value, AsyncHttpApiError)
    assert caught.value.status_code == 401
    assert len(transport.calls) == 1


def test_parse_submission_authorization_invalid_raise_AuthenticationError() -> None:
    """HTTP200でも認証拒否コードを認証例外として扱う"""
    # Given: 公式の認証拒否コード
    body = b'{"code":"-","message":"received illegal service authorization","text":""}'
    # When: 受付失敗を解析する
    with pytest.raises(AuthenticationError) as caught:
        parse_submission(body)
    # Then: 非同期エラーの詳細も失わない
    assert isinstance(caught.value, AsyncHttpApiError)
    assert caught.value.code == "-" and caught.value.status_code == 200
