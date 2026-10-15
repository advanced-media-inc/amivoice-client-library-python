"""非同期HTTPのCLIを外部APIなしで検証する"""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from amivoice import AmiVoiceAsyncClient, AsyncJobTimeoutError
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


@pytest.mark.parametrize("operation", ["submit", "status", "wait"])
@pytest.mark.parametrize("recursion_error", [False, True])
def test_async_example_json_decoding_invalid_return_error(
    operation: str, recursion_error: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """深い不正JSONとデコーダーの再帰エラーを安全に表示する"""
    # Given: 深い不正JSONまたは正常な応答で再帰エラーを発生させるデコーダー
    monkeypatch.setenv("AMIVOICE_API_KEY", "dummy")
    if recursion_error:
        data = {"sessionid": "job1"} if operation == "submit" else queued()
        body = json.dumps({**data, "extra": "sensitive"}).encode()
        monkeypatch.setattr(json, "loads", Mock(side_effect=RecursionError("sensitive decoder detail")))
    else:
        depth = 100_000
        body = b'{"extra":' + b"[" * depth + b'"sensitive"' + b"]" * depth + b"}"
    transport = RecordingTransport([(200, body)])
    monkeypatch.setattr(
        async_http_tester, "AmiVoiceAsyncClient", lambda **settings: AmiVoiceAsyncClient(**settings, transport=transport)
    )
    path = tmp_path / "audio.wav"
    path.write_bytes(b"audio")
    # When: 各サブコマンドを実行する
    result = async_http_tester.main([operation, str(path) if operation == "submit" else "job1"])
    # Then: 生本文やトレースバックを出さず終了コード1を返す
    output = capsys.readouterr()
    assert result == 1
    assert "Async HTTP failed:" in output.err
    assert "sensitive" not in output.err and "Traceback" not in output.err
    assert output.out == ""


@pytest.mark.parametrize("flag", ["--speaker-diarization", "--no-speaker-diarization", None])
def test_async_example_diarization_valid_return_settings_and_wire(
    flag: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CLIから新設定の指定・否定・未指定をRecognitionSettingsへ渡す"""
    # Given: フェイクの通信処理と音声ファイル
    monkeypatch.setenv("AMIVOICE_API_KEY", "dummy")
    transport = RecordingTransport([{"sessionid": "job1", "text": "..."}])
    monkeypatch.setattr(
        async_http_tester, "AmiVoiceAsyncClient", lambda **kwargs: AmiVoiceAsyncClient(**kwargs, transport=transport)
    )
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    arguments = ["submit", str(audio)]
    if flag is not None:
        arguments.extend([flag, "--diarization-min-speaker", "1", "--diarization-max-speaker", "20"])
    # When: CLIを実行する
    assert async_http_tester.main(arguments) == 0
    # Then: True/Falseを大文字始まりで送信し、未指定は送信しない
    body = transport.calls[0][3]
    if flag is None:
        assert all(key not in body for key in (b"speakerDiarization", b"diarizationMinSpeaker", b"diarizationMaxSpeaker"))
    else:
        enabled = flag == "--speaker-diarization"
        assert f"speakerDiarization={enabled}".encode() in body
        assert b"diarizationMinSpeaker=1" in body and b"diarizationMaxSpeaker=20" in body


@pytest.mark.parametrize("arguments", [["submit", "audio.wav", "--diarization-min-speaker", "bad"], ["unknown"]])
def test_async_example_syntax_invalid_raise_exit_two(arguments: list[str]) -> None:
    """構文エラーの終了コード2を維持する"""
    # Given: argparseで解析できない指定
    # When / Then: キー確認や通信より前に終了する
    with pytest.raises(SystemExit) as caught:
        async_http_tester.main(arguments)
    assert caught.value.code == 2


def test_async_example_invalid_count_invalid_return_exit_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """設定エラーは音声読込・通信より前に終了コード1を返す"""
    # Given: 不正な話者数
    monkeypatch.setenv("AMIVOICE_API_KEY", "dummy")
    transport = RecordingTransport([])
    monkeypatch.setattr(
        async_http_tester, "AmiVoiceAsyncClient", lambda **kwargs: AmiVoiceAsyncClient(**kwargs, transport=transport)
    )
    # When: 整数だが範囲外の値でsubmitする
    result = async_http_tester.main(["submit", "does-not-exist.wav", "--speaker-diarization", "--diarization-min-speaker", "21"])
    # Then: 従来のエラー終了コードを維持する
    assert result == 1 and not transport.calls


def test_async_example_timeout_edge_return_exit_three(monkeypatch: pytest.MonkeyPatch) -> None:
    """待機上限の終了コード3を維持する"""

    # Given: 全体の待機上限を迎えたクライアント
    def timeout_wait(self: AmiVoiceAsyncClient, session_id: str, **kwargs: object) -> None:
        raise AsyncJobTimeoutError(session_id, None)

    monkeypatch.setenv("AMIVOICE_API_KEY", "dummy")
    monkeypatch.setattr(AmiVoiceAsyncClient, "wait", timeout_wait)
    # When: 保存済みIDの完了を待機する
    result = async_http_tester.main(["wait", "job1", "--timeout", "1"])
    # Then: キャンセルせず同じ終了コードを返す
    assert result == 3
