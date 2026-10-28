"""WebSocket認識の簡易サンプル、認証はAMIVOICE_API_KEYのみを使う"""

from collections.abc import Sequence

if __package__:
    from .recognition_cli import RecognitionTester
else:
    from recognition_cli import RecognitionTester


def main(arguments: Sequence[str] | None = None) -> int:
    """公開APIで音声ファイルを認識する

    Args:
        arguments (Sequence[str] | None): CLI引数

    Returns:
        int: CLI終了コード
    """
    return RecognitionTester("ws", simple=True).run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
