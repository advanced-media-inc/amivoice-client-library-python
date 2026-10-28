"""非同期HTTPの構造化エラーと安全な表示を検証する"""

import json
from unittest.mock import Mock

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


@pytest.mark.parametrize("operation", ["submit", "get_job", "wait"])
def test_request_json_recursion_error_invalid_raise_AsyncHttpApiError(operation: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """JSONデコーダーの再帰エラーでも公開例外と元の本文を保持する"""
    # Given: 正常な応答でも再帰エラーを発生させるJSONデコーダー
    data = {"sessionid": "job1"} if operation == "submit" else {"session_id": "job1", "status": "queued"}
    body = json.dumps({**data, "extra": "sensitive"}).encode()
    # ネスト深度での再帰エラー発生はPythonのバージョンやビルドに依存する
    monkeypatch.setattr(json, "loads", Mock(side_effect=RecursionError("sensitive decoder detail")))
    transport = RecordingTransport([(200, body)])
    client = AmiVoiceAsyncClient(
        api_key="dummy", settings=RecognitionSettings(grammar_file_names="-a-general"), transport=transport
    )
    # When: 受付又は状態取得の応答を解析する
    with pytest.raises(AsyncHttpApiError) as caught:
        if operation == "wait":
            client.wait("job1", raise_on_error=False)
        else:
            getattr(client, operation)(b"audio" if operation == "submit" else "job1")
    # Then: RecursionErrorを漏らさず、再試行や生本文のログ出力を行わない
    error = caught.value
    assert error.status_code == 200
    assert error.raw_body == body
    assert error.data is None
    assert error.session_id == (None if operation == "submit" else "job1")
    assert "sensitive" not in str(error)
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


@pytest.mark.parametrize("http_rejection", [False, True])
def test_submit_diarization_rejected_valid_raise_existing_api_error(http_rejection: bool) -> None:
    """話者設定有効時も一般の受付拒否経路を利用し固有コードを創作しない"""
    # Given: 公式の受付拒否形式または一般のHTTP拒否の合成応答（実音声長の実証ではない）
    response = {"code": "o", "message": "rejected", "text": "", "results": []}
    body = json.dumps(response).encode()
    transport = RecordingTransport([(400 if http_rejection else 200, body)])
    client = AmiVoiceAsyncClient(
        api_key="dummy",
        transport=transport,
        settings=RecognitionSettings(grammar_file_names="-a-general", speaker_diarization=True),
    )
    # When / Then: 既存の構造化APIエラーを返し自動再送しない
    with pytest.raises(AsyncHttpApiError) as caught:
        client.submit(b"synthetic-audio")
    assert caught.value.raw_body == body and caught.value.code == "o"
    assert len(transport.calls) == 1
    assert b"speakerDiarization=True" in transport.calls[0][3]
