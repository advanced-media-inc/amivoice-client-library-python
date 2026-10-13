"""非同期HTTPのCLIを外部APIなしで検証する"""

from pathlib import Path

import pytest

from amivoice import AmiVoiceAsyncClient
from examples import async_http_tester

from .amivoice.test_async_client import RecordingTransport, completed, queued


@pytest.mark.parametrize("arguments", [["--help"], ["submit", "--help"], ["status", "--help"], ["wait", "--help"]])
def test_async_example_help_no_auth_valid_return_zero(arguments: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    """各helpはキーなしで実行できる"""
    # Given: 認証しないhelp操作
    # When: 引数を解析する
    with pytest.raises(SystemExit) as caught:
        async_http_tester.main(arguments)
    # Then: キーをCLI引数へ渡さない
    assert caught.value.code == 0
    assert "--api-key" not in capsys.readouterr().out


@pytest.mark.parametrize("operation", ["submit", "status", "wait"])
def test_async_example_public_client_valid_return_result(
    operation: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """公開クライアントを使い受付ID、状態、認識結果を表示する"""
    # Given: ダミーキーと合成応答
    monkeypatch.setenv("AMIVOICE_API_KEY", "dummy")
    response = (
        {"sessionid": "job1", "text": "..."} if operation == "submit" else queued() if operation == "status" else completed()
    )
    transport = RecordingTransport([response])
    monkeypatch.setattr(
        async_http_tester, "AmiVoiceAsyncClient", lambda **settings: AmiVoiceAsyncClient(**settings, transport=transport)
    )
    path = tmp_path / "audio.wav"
    path.write_bytes(b"audio")
    # When: 1操作だけ実行する
    result = async_http_tester.main([operation, str(path) if operation == "submit" else "job1"])
    # Then: 非同期APIをawaitせず利用する
    assert result == 0
    output = capsys.readouterr().out
    assert ("job1" if operation == "submit" else "queued" if operation == "status" else "認識") in output
