"""公開 API を使った HTTP 認識の複数ファイル・設定サンプル"""

import argparse
import time

from amivoice import AmiVoiceClient
from amivoice.exceptions import AmiVoiceError


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
        "domain-id",
        "result-encoding",
        "voice-detection",
        "audio-filter-properties",
    ]:
        parser.add_argument("--" + name)
    for name in [
        "recognition-timeout",
        "complete-timeout",
        "result-updated-interval",
        "max-decoding-time",
        "max-response-time",
        "target-response-time",
        "selected-channel",
    ]:
        parser.add_argument("--" + name, type=int)
    for name in ["confidence-level", "wildcard-model-penalty", "max-decoding-rate", "target-decoding-rate"]:
        parser.add_argument("--" + name, type=float)
    args = parser.parse_args(arguments)
    if args.loop < 1:
        parser.error("--loop must be positive")
    options = vars(args).copy()
    for name in ("url", "audio_files", "loop"):
        options.pop(name)
    start = time.monotonic()
    try:
        client = AmiVoiceClient(http_api_url=args.url, **options)
        for _ in range(args.loop):
            for audio_file in args.audio_files:
                result = client.transcribe(audio_file)
                print(f"C {result.session_id}")
                print(f"F {result.raw}")
                print(f" -> {result.text}")
    except (AmiVoiceError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"INFO: elapsed time: {(time.monotonic() - start) * 1000:.3f} [msec.]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
