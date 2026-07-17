"""AmiVoice クライアントで使用する共通型定義。"""

from pathlib import Path
from typing import BinaryIO

AudioSource = bytes | BinaryIO | str | Path

__all__ = [
    "AudioSource",
]
