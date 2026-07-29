"""音声ソース解決ユーティリティ。"""

from pathlib import Path

from ._types import AudioSource


def resolve_audio(audio: AudioSource) -> bytes:
    """bytes・パス・バイナリストリームを生の音声バイト列に正規化する。

    Args:
        audio: 音声ソース（bytes・バイナリストリーム・ファイルパス）。

    Returns:
        音声データのバイト列。

    Raises:
        TypeError: サポートされていない音声ソース型の場合。
    """
    if isinstance(audio, bytes):
        return audio
    if isinstance(audio, (str, Path)):
        with Path(audio).open("rb") as fp:
            return fp.read()
    read = getattr(audio, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, bytes):
            return data
        if isinstance(data, bytearray):
            return bytes(data)
        raise TypeError("Binary stream read() must return bytes")
    raise TypeError("Unsupported audio source type")
