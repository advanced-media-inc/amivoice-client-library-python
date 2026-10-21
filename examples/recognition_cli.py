"""公開APIのみを使用し、APIキーをコマンドラインへ渡さない認識サンプル"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from amivoice import AmiVoiceClient, AmiVoiceError, Codec, Engine, RecognitionSettings, StreamEvent


class RecognitionTester:
    """HTTPとWebSocketの使用例で引数解析と結果表示を共有する"""

    def __init__(self, interface: Literal["http", "ws"], *, simple: bool = False) -> None:
        """対応するインタフェースの公式設定だけを公開する

        Args:
            interface (Literal["http", "ws"]): 通信方式
            simple (bool): 最小限の設定のみを表示するか
        """
        self.interface = interface
        self.parser = argparse.ArgumentParser(description="Recognize audio using AMIVOICE_API_KEY from the environment")
        self.parser.add_argument("audio", type=Path, nargs=None if simple else "+", help="Audio file path")
        self.parser.add_argument("--engine", default=Engine.A_GENERAL.value, help="Engine name, e.g. --engine=-a-general")
        self.parser.add_argument(
            "--codec", type=Codec, default=Codec.HEADER_16K, help="Official audio format, e.g. 16K or LSB16K"
        )
        self.parser.add_argument("--url", help="Override the service endpoint")
        self.parser.add_argument(
            "--logging-opt-out", action="store_true", help="Use a nolog endpoint; custom URL must have nolog path"
        )
        self.parser.add_argument("--connect-timeout", type=int, default=10000, help="Connect timeout in milliseconds")
        self.parser.add_argument("--receive-timeout", type=int, default=30000, help="Receive timeout in milliseconds")
        if interface == "ws":
            self.parser.add_argument("--chunk-size", type=self._positive_size, default=4096, help="Audio chunk size in bytes")
        if not simple:
            self._add_detailed_arguments()

    @staticmethod
    def _positive_size(value: str) -> int:
        result = int(value)
        if result <= 0:
            raise argparse.ArgumentTypeError("Chunk size must be positive")
        return result

    def _add_detailed_arguments(self) -> None:
        self.parser.add_argument("--profile-id", help="Read-only dictionary reference, e.g. :user01")
        self.parser.add_argument("--profile-words", help="Session word definitions in official format")
        self.parser.add_argument("--segmenter-properties", help="Official VAD, diarization or language properties")
        self.parser.add_argument("--confidence-level", type=float)
        self.parser.add_argument("--keep-filler-token", action=argparse.BooleanOptionalAction, default=None)
        self.parser.add_argument("--billing-key", help="Usage aggregation tag")
        self.parser.add_argument("--recognition-timeout", type=int)
        self.parser.add_argument("--max-decoding-time", type=int)
        self.parser.add_argument("--max-response-time", type=int)
        self.parser.add_argument("--max-decoding-rate", type=float)
        self.parser.add_argument("--target-response-time", type=int)
        self.parser.add_argument("--target-decoding-rate", type=float)
        if self.interface == "http":
            self.parser.add_argument("--selected-channel", type=int, help="Select one audio channel")
        else:
            self.parser.add_argument("--result-updated-interval", type=int)
            self.parser.add_argument("--no-input-timeout", type=int)
            self.parser.add_argument("--show-events", action="store_true", help="Print partial results and utterance events")

    def _create_client(self, arguments: argparse.Namespace) -> AmiVoiceClient:
        settings = {
            "grammar_file_names": arguments.engine,
            "codec": arguments.codec,
            "logging_opt_out": arguments.logging_opt_out,
        }
        for name in (
            "profile_id",
            "profile_words",
            "segmenter_properties",
            "confidence_level",
            "keep_filler_token",
            "billing_key",
            "recognition_timeout",
            "max_decoding_time",
            "max_response_time",
            "max_decoding_rate",
            "target_response_time",
            "target_decoding_rate",
            "selected_channel",
            "result_updated_interval",
            "no_input_timeout",
        ):
            value = getattr(arguments, name, None)
            if value is not None:
                settings[name] = value
        connection = {
            "connect_timeout": arguments.connect_timeout,
            "receive_timeout": arguments.receive_timeout,
        }
        if arguments.url is not None:
            connection["http_api_url" if self.interface == "http" else "ws_api_url"] = arguments.url
        return AmiVoiceClient(settings=RecognitionSettings(**settings), **connection)

    @staticmethod
    def _print_event(event: StreamEvent, *, show_events: bool) -> None:
        if event.is_final:
            print(event.text)
            if event.result.is_error:
                print(f"Recognition failed: code={event.result.data['code']}", file=sys.stderr)
        elif show_events:
            if event.utterance is not None:
                print(f"{event.type}: {event.utterance.time}")
            elif event.is_partial:
                print(f"partial: {event.text}")

    def _recognize_stream(self, client: AmiVoiceClient, path: Path, arguments: argparse.Namespace) -> bool:
        with path.open("rb") as audio, client.stream() as session:
            for chunk in iter(lambda: audio.read(arguments.chunk_size), b""):
                session.write(chunk)
                for event in session.poll():
                    self._print_event(event, show_events=getattr(arguments, "show_events", False))
            session.end()
            for event in session.poll():
                self._print_event(event, show_events=getattr(arguments, "show_events", False))
            results = session.results()
        return bool(results) and not any(result.is_error for result in results)

    def run(self, arguments: Sequence[str] | None = None) -> int:
        """環境変数で認証し、通信または認識の失敗を終了コードへ反映する

        Args:
            arguments (Sequence[str] | None): CLI引数、省略時はsys.argv

        Returns:
            int: 正常終了は0、通信・認識・ファイルエラーは1
        """
        parsed = self.parser.parse_args(arguments)
        paths = parsed.audio if isinstance(parsed.audio, list) else [parsed.audio]
        try:
            client = self._create_client(parsed)
            succeeded = True
            for path in paths:
                if self.interface == "http":
                    print(client.transcribe(path).text)
                else:
                    succeeded = self._recognize_stream(client, path, parsed) and succeeded
            return 0 if succeeded else 1
        except (AmiVoiceError, OSError) as error:
            print(f"Recognition failed: {error}", file=sys.stderr)
            return 1
