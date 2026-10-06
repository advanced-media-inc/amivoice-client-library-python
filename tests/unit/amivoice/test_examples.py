"""公開 API へ移行したサンプルスクリプトの CLI テスト"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from examples import hrp_simple_tester, hrp_tester, wrp_simple_tester, wrp_tester

from ._recognition_fakes import make_http_transport, make_websocket_transport


def test_hrp_simple_example_engine_prefix_valid_return_result(capsys: pytest.CaptureFixture[str]) -> None:
    """ハイフン付き接続エンジンと環境変数認証を公開 API へ渡す"""
    # Given: HTTP 認識モック
    transport = make_http_transport()
    # When: 既存の位置引数形式で実行する
    with (
        patch("amivoice.client._construct_hrp_transport", return_value=transport),
        patch.dict("os.environ", AMIVOICE_API_KEY="test"),
    ):
        status = hrp_simple_tester.main(["http://example.com/", "unused.wav", "16K", "-a-general"])
    # Then: ファイルエラーは CLI のエラー終了として扱う
    assert status == 1
    assert "ERROR:" in capsys.readouterr().out


def test_hrp_simple_example_audio_valid_return_result(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """簡易 HTTP サンプルが位置引数を欠損なく転送する"""
    # Given: 音声ファイルと HTTP モック
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    transport = make_http_transport()
    # When: ハイフン付きエンジンと API キーを指定する
    with patch("amivoice.client._construct_hrp_transport", return_value=transport):
        status = hrp_simple_tester.main(["http://example.com/", str(audio), "16K", "-a-general", "test"])
    # Then: 音声とエンジンが公開 API へ届く
    assert status == 0
    assert transport.transcribe.call_args.args[2].grammar_file_names == "-a-general"
    assert transport.transcribe.call_args.args[3] == b"audio"
    assert "hello" in capsys.readouterr().out


def test_hrp_example_result_encoding_unsupported_raise_SystemExit(capsys: pytest.CaptureFixture[str]) -> None:
    """効果のない文字コード指定の CLI オプションを拒否する"""
    with patch("examples.hrp_tester.AmiVoiceClient") as factory, pytest.raises(SystemExit) as error:
        hrp_tester.main(["http://example.com/", "audio.wav", "--result-encoding=SHIFT_JIS"])
    assert error.value.code == 2
    assert "unrecognized arguments: --result-encoding=SHIFT_JIS" in capsys.readouterr().err
    factory.assert_not_called()


def test_hrp_example_typed_options_valid_return_result(tmp_path: Path) -> None:
    """詳細 HTTP サンプルの数値と真偽値を typed 設定へ変換する"""
    # Given: 音声ファイルと認識モック
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    transport = make_http_transport()
    # When: 複数回の認識を CLI から実行する
    with (
        patch("amivoice.client._construct_hrp_transport", return_value=transport),
        patch.dict("os.environ", AMIVOICE_API_KEY="test"),
    ):
        status = hrp_tester.main(
            [
                "http://example.com/",
                str(audio),
                "--grammar-file-names=-a-general",
                "--codec",
                "16K",
                "--confidence-level",
                "0.3",
                "--no-keep-filler-token",
                "--max-decoding-time",
                "1000",
                "--loop",
                "2",
            ]
        )
    # Then: 2 回独立して認識し入力型を維持する
    assert status == 0
    assert transport.transcribe.call_count == 2
    params = transport.transcribe.call_args.args[2]
    assert params.confidence_level == 0.3
    assert params.keep_filler_token is False
    assert params.max_decoding_time == 1000


@pytest.mark.parametrize("simple", [True, False])
def test_wrp_example_audio_valid_return_result(simple: bool, tmp_path: Path) -> None:
    """WebSocket の両サンプルが公開ストリーム API で音声を送信する"""
    # Given: 音声ファイルと WebSocket モック
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    transport = make_websocket_transport()
    # When: 簡易版または詳細版を実行する
    with (
        patch("amivoice._stream._connect_websocket_transport", return_value=transport),
        patch.dict("os.environ", AMIVOICE_API_KEY="test"),
    ):
        if simple:
            status = wrp_simple_tester.main(["wss://example.com/", str(audio), "16K", "-a-general"])
        else:
            status = wrp_tester.main(["wss://example.com/", str(audio), "--grammar-file-names=-a-general", "--codec", "16K"])
    # Then: WRP 音声コマンドが届き接続を閉じる
    assert status == 0
    transport.send_binary.assert_called_once_with(b"paudio")
    transport.close.assert_called_once()


def test_wrp_example_negative_interval_invalid_raise_SystemExit() -> None:
    """送信間隔の不正値を通信前に拒否する"""
    # Given / When / Then: 不正な CLI 引数
    with patch("examples.wrp_tester.AmiVoiceClient", MagicMock()) as factory, pytest.raises(SystemExit):
        wrp_tester.main(["wss://example.com/", "audio.wav", "--interval-ms=-1"])
    factory.assert_not_called()
