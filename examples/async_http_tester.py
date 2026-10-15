"""非同期HTTP v2の作成・取得・待機CLI、Python async/await対応ではない"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from amivoice import (
    AmiVoiceAsyncClient,
    AmiVoiceError,
    AsyncJobSnapshot,
    AsyncJobTimeoutError,
    Codec,
    Engine,
    RecognitionSettings,
)


class AsyncHttpTester:
    """APIキーをCLI引数に含めず、ジョブ操作を公開APIから実行する"""

    def __init__(self) -> None:
        """基本認識に対応するサブコマンドを用意する"""
        self.parser = argparse.ArgumentParser(
            description="AmiVoice async HTTP v2 jobs (blocking Python methods); uses AMIVOICE_API_KEY"
        )
        self.parser.add_argument("--url", help="Override v2 HTTPS endpoint (loopback HTTP is allowed for tests)")
        self.parser.add_argument("--proxy-server-name", help="HTTP proxy; avoid exposing credentials on the command line")
        self.parser.add_argument("--connect-timeout", type=int, default=10000, help="Connect timeout in milliseconds")
        self.parser.add_argument("--receive-timeout", type=int, default=30000, help="Socket timeout in milliseconds")
        commands = self.parser.add_subparsers(dest="operation", required=True)
        submit = commands.add_parser("submit", help="Upload audio and print its job ID without waiting for recognition")
        submit.add_argument("audio", type=Path)
        submit.add_argument("--engine", default=Engine.A_GENERAL.value, help="Engine, e.g. --engine=-a-general")
        submit.add_argument("--codec", type=Codec, help="Audio format (omit for audio with a header)")
        submit.add_argument("--logging-opt-out", action=argparse.BooleanOptionalAction, default=None)
        submit.add_argument("--content-id")
        submit.add_argument("--compatible-with-sync", action=argparse.BooleanOptionalAction, default=None)
        submit.add_argument("--speaker-diarization", action=argparse.BooleanOptionalAction, default=None)
        submit.add_argument("--diarization-min-speaker", type=int, default=None)
        submit.add_argument("--diarization-max-speaker", type=int, default=None)
        submit.add_argument("--profile-id")
        submit.add_argument("--profile-words")
        submit.add_argument("--segmenter-properties", help="VAD or language identification; not sync diarization")
        submit.add_argument("--selected-channel", type=int)
        submit.add_argument("--confidence-level", type=float)
        submit.add_argument("--keep-filler-token", action=argparse.BooleanOptionalAction, default=None)
        submit.add_argument("--billing-key")
        for name in ("recognition-timeout", "max-decoding-time", "max-response-time", "target-response-time"):
            submit.add_argument("--" + name, type=int)
        for name in ("max-decoding-rate", "target-decoding-rate"):
            submit.add_argument("--" + name, type=float)
        status = commands.add_parser("status", help="Fetch the current status and available recognition text")
        status.add_argument("session_id")
        wait = commands.add_parser("wait", help="Block until a saved job ID completes; timeout does not cancel the server job")
        wait.add_argument("session_id")
        wait.add_argument("--poll-interval", type=float, default=10.0, help="Polling interval in seconds")
        wait.add_argument("--timeout", type=float, help="Total wait seconds (omit for unlimited)")

    @staticmethod
    def _show(snapshot: AsyncJobSnapshot) -> int:
        print(f"{snapshot.session_id}: {snapshot.status}")
        if snapshot.recognition is not None:
            print(snapshot.recognition.text)
        if snapshot.is_error:
            print("Job or recognition failed; inspect the API result using get_job()", file=sys.stderr)
            return 1
        return 0

    @staticmethod
    def _client(arguments: argparse.Namespace) -> AmiVoiceAsyncClient:
        options = {
            "connect_timeout": arguments.connect_timeout,
            "receive_timeout": arguments.receive_timeout,
            "proxy_server_name": arguments.proxy_server_name,
        }
        if arguments.url is not None:
            options["api_url"] = arguments.url
        return AmiVoiceAsyncClient(**options)

    def run(self, arguments: Sequence[str] | None = None) -> int:
        """状態と認識テキストだけを表示し、生の応答を無条件にログへ出さない

        Args:
            arguments (Sequence[str] | None): 引数、省略時はsys.argv

        Returns:
            int: 成功0、エラー1、待機タイムアウト3、構文エラーはargparseの2
        """
        parsed = self.parser.parse_args(arguments)
        try:
            client = self._client(parsed)
            if parsed.operation == "submit":
                options = vars(parsed).copy()
                for name in ("operation", "audio", "url", "proxy_server_name", "connect_timeout", "receive_timeout"):
                    options.pop(name)
                options["grammar_file_names"] = options.pop("engine")
                print(client.submit(parsed.audio, settings=RecognitionSettings(**options)).session_id)
                return 0
            if parsed.operation == "status":
                return self._show(client.get_job(parsed.session_id))
            snapshot = client.wait(parsed.session_id, poll_interval=parsed.poll_interval, timeout=parsed.timeout)
            return self._show(snapshot)
        except AsyncJobTimeoutError as error:
            print(f"Wait timed out for job {error.session_id}; resume with the same ID", file=sys.stderr)
            return 3
        except (AmiVoiceError, OSError) as error:
            print(f"Async HTTP failed: {error}", file=sys.stderr)
            return 1


def main(arguments: Sequence[str] | None = None) -> int:
    """使用例CLIを開始する

    Args:
        arguments (Sequence[str] | None): コマンド引数

    Returns:
        int: 終了コード
    """
    return AsyncHttpTester().run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
