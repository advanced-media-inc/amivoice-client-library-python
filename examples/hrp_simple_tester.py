"""公開 API を使った HTTP 音声認識の簡易サンプル"""

import argparse
import sys

from amivoice import transcribe
from amivoice.exceptions import AmiVoiceError


def main(arguments: list[str] | None = None) -> int:
    """URL・音声ファイル・コーデック・エンジンを指定して認識する

    Args:
        arguments (list[str] | None): CLI 引数、省略時は sys.argv

    Returns:
        int: 成功は 0、認識またはファイルのエラーは 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("audio_file")
    parser.add_argument("codec")
    parser.add_argument("grammar_file_names")
    parser.add_argument("api_key", nargs="?", help="省略時は AMIVOICE_API_KEY")
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    # 接続エンジン名の先頭の - を CLI オプションとして解釈させない
    if len(arguments) >= 4 and "--" not in arguments:
        arguments.insert(3, "--")
    args = parser.parse_args(arguments)
    try:
        result = transcribe(
            args.audio_file, api_key=args.api_key, api_url=args.url, codec=args.codec, grammar_file_names=args.grammar_file_names
        )
        print(result.raw)
        print(f" -> {result.text}")
    except (AmiVoiceError, OSError) as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
