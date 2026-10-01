"""公開 API を使った WebSocket 認識の複数ファイル・設定サンプル"""

import argparse
import time
from pathlib import Path

from amivoice import AmiVoiceClient
from amivoice.exceptions import AmiVoiceError


def stream_audio_file(client: AmiVoiceClient, audio_file: str, interval_ms: float) -> None:
    """音声ファイルを指定間隔で送信し、イベントを受信順に表示する

    Args:
        client (AmiVoiceClient): 認識クライアント
        audio_file (str): 音声ファイルのパス
        interval_ms (float): チャンクの送信間隔（ミリ秒）
    """
    with Path(audio_file).open("rb") as audio, client.stream() as session:
        while chunk := audio.read(4096):
            session.write(chunk)
            for event in session.poll():
                print(f"{event.type}: {event.text}")
            if interval_ms:
                time.sleep(interval_ms / 1000)
        session.end()
        for event in session.events():
            print(f"{event.type}: {event.text}")


def main(arguments: list[str] | None = None) -> int:
    """設定と繰り返し回数を指定して複数の音声ファイルを認識する

    Args:
        arguments (list[str] | None): CLI 引数、省略時は sys.argv

    Returns:
        int: 成功は 0、認識またはファイルのエラーは 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("audio_files", nargs="+")
    parser.add_argument("--loop", type=int, default=1)
    parser.add_argument("--logging-opt-out", action="store_true")
    parser.add_argument("--connect-timeout", type=int, default=5000, help="ミリ秒")
    parser.add_argument("--receive-timeout", type=int, default=0, help="ミリ秒、0 は無制限")
    parser.add_argument("--keep-filler-token", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--interval-ms", type=float, default=0, help="音声チャンクの送信間隔")
    for name in [
        "grammar-file-names",
        "codec",
        "result-type",
        "profile-id",
        "profile-words",
        "segmenter-type",
        "segmenter-properties",
        "extension",
        "billing-key",
        "mode",
        "proxy-server-name",
    ]:
        parser.add_argument("--" + name)
    for name in [
        "recognition-timeout",
        "complete-timeout",
        "result-updated-interval",
        "max-decoding-time",
        "max-response-time",
        "target-response-time",
        "no-input-timeout",
    ]:
        parser.add_argument("--" + name, type=int)
    for name in ["confidence-level", "wildcard-model-penalty", "max-decoding-rate", "target-decoding-rate"]:
        parser.add_argument("--" + name, type=float)
    args = parser.parse_args(arguments)
    if args.loop < 1:
        parser.error("--loop must be positive")
    if args.interval_ms < 0:
        parser.error("--interval-ms must be non-negative")
    options = vars(args).copy()
    for name in ("url", "audio_files", "loop", "interval_ms"):
        options.pop(name)
    start = time.monotonic()
    try:
        client = AmiVoiceClient(ws_api_url=args.url, **options)
        for _ in range(args.loop):
            for audio_file in args.audio_files:
                stream_audio_file(client, audio_file, args.interval_ms)
    except (AmiVoiceError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"INFO: elapsed time: {(time.monotonic() - start) * 1000:.3f} [msec.]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
