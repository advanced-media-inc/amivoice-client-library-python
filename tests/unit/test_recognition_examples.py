"""4つの使用例をダミーキーと公開APIのテスト通信処理で検証する"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from amivoice import AmiVoiceClient
from examples import hrp_simple_tester, hrp_tester, recognition_cli, wrp_simple_tester, wrp_tester

from .amivoice.test_amivoice_client import HttpFake, WebSocketFake

EXAMPLE_MODULES = {
    "hrp_simple_tester": hrp_simple_tester,
    "hrp_tester": hrp_tester,
    "wrp_simple_tester": wrp_simple_tester,
    "wrp_tester": wrp_tester,
}


@pytest.mark.parametrize("module_name", EXAMPLE_MODULES)
def test_example_help_without_auth_valid_return_usage(module_name: str, capsys: pytest.CaptureFixture[str]) -> None:
    """import時にCLIを実行せず、キーなしでもhelpを表示できる"""
    # Given: 環境に実キーがない状態
    module = EXAMPLE_MODULES[module_name]
    # When: helpのみを要求する
    with pytest.raises(SystemExit) as caught:
        module.main(["--help"])
    # Then: 認証情報を引数として受け付けない
    assert caught.value.code == 0
    output = capsys.readouterr().out
    assert "AMIVOICE_API_KEY" in output
    assert "--api-key" not in output
    assert "--result-type" not in output


@pytest.mark.parametrize("module_name", EXAMPLE_MODULES)
def test_example_direct_script_help_valid_return_zero(module_name: str) -> None:
    """モジュールimportと直接スクリプト実行の両方で起動できる"""
    # Given: リポジトリ内のスクリプト
    root = Path(__file__).resolve().parents[2]
    # When: ネットワークを使わないhelpを別プロセスで実行する
    completed = subprocess.run(
        [sys.executable, str(root / "examples" / (module_name + ".py")), "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    # Then: srcや旧パッケージのsys.path追加を必要としない
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("module_name", EXAMPLE_MODULES)
def test_example_public_api_valid_return_recognized_text(
    module_name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ENV認証で公開APIを呼び、WebSocketの終了後の結果も表示する"""
    # Given: ダミー環境変数とフェイク通信、実ファイルを用意する
    monkeypatch.setenv("AMIVOICE_API_KEY", "dummy")
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"sample-audio")
    body = {"text": "recognized", "code": "", "message": ""}
    http = HttpFake(body)
    ws = WebSocketFake(["A " + json.dumps(body)])
    created = []

    def create_client(**kwargs: object) -> AmiVoiceClient:
        created.append(kwargs)
        return AmiVoiceClient(**kwargs, hrp_transport=http, wrp_transport=ws)

    monkeypatch.setattr(recognition_cli, "AmiVoiceClient", create_client)
    module = EXAMPLE_MODULES[module_name]
    # When: 1つのファイルを認識する
    status = module.main([str(audio), "--logging-opt-out"])
    # Then: キーをargsへ渡さず公開APIで結果を取得する
    assert status == 0
    assert "recognized" in capsys.readouterr().out
    assert "api_key" not in created[0]
    if module_name.startswith("wrp"):
        assert ws.sent[-1] == "e"
        assert ws.closed
        assert ws.sent[1] == b"sample-audio"
    else:
        assert http.calls[0][0].endswith("/nolog/recognize")


@pytest.mark.parametrize("module_name", EXAMPLE_MODULES)
def test_example_missing_key_invalid_return_error(module_name: str, tmp_path: Path) -> None:
    """認証情報がなければ通信を試みず失敗終了する"""
    # Given: 有効なファイルと認証なしの環境
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"sample")
    module = EXAMPLE_MODULES[module_name]
    # When / Then: ネットワークガードを発動させる前に拒否する
    assert module.main([str(audio)]) == 1


@pytest.mark.parametrize("flag", ["--selected-channel", "--result-updated-interval", "--no-input-timeout"])
def test_example_interface_specific_setting_invalid_reject_wrong_interface(flag: str) -> None:
    """専用設定を他インタフェースのCLIに公開しない"""
    # Given: 別インタフェース専用の設定
    tester = recognition_cli.RecognitionTester("ws" if flag == "--selected-channel" else "http")
    # When / Then: 引数解析時に拒否し、通信しない
    with pytest.raises(SystemExit) as caught:
        tester.run(["test.wav", flag, "0"])
    assert caught.value.code == 2


def test_example_chunk_size_zero_invalid_reject_before_network() -> None:
    """空読み込みによる音声未送信を防ぐ"""
    # Given: WebSocket使用例
    tester = recognition_cli.RecognitionTester("ws")
    # When / Then: ゼロのchunk-sizeを送信前に拒否する
    with pytest.raises(SystemExit):
        tester.run(["test.wav", "--chunk-size", "0"])


def test_example_stream_rejected_result_invalid_return_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """正常なe応答でも、認識結果のcode oを成功扱いしない"""
    # Given: 拒否を返すWebSocket接続
    monkeypatch.setenv("AMIVOICE_API_KEY", "dummy")
    audio = tmp_path / "test.wav"
    audio.write_bytes(b"sample")
    fake = WebSocketFake(['A {"text":"","code":"o","message":"rejected"}'])
    monkeypatch.setattr(recognition_cli, "AmiVoiceClient", lambda **kwargs: AmiVoiceClient(**kwargs, wrp_transport=fake))
    # When: 送信と終了待機を行う
    status = recognition_cli.RecognitionTester("ws").run([str(audio)])
    # Then: 拒否結果を終了コードと表示へ反映する
    assert status == 1
    assert "code=o" in capsys.readouterr().err
