"""音声コーデックと接続エンジン名の定数。"""

from enum import StrEnum
from typing import Self

__all__ = ["Codec"]


class Codec(StrEnum):
    """AmiVoice APIで指定できる音声フォーマット名。"""

    # Pythonでは変数名の先頭に数字を使用できないため、冗長ですがCODEC_を付けています
    CODEC_8K = "8K"
    CODEC_16K = "16K"
    LSB8K = "LSB8K"
    LSB11K = "LSB11K"
    LSB16K = "LSB16K"
    LSB22K = "LSB22K"
    LSB32K = "LSB32K"
    LSB44K = "LSB44K"
    LSB48K = "LSB48K"
    MSB8K = "MSB8K"
    MSB11K = "MSB11K"
    MSB16K = "MSB16K"
    MSB22K = "MSB22K"
    MSB32K = "MSB32K"
    MSB44K = "MSB44K"
    MSB48K = "MSB48K"
    MULAW = "MULAW"
    ALAW = "ALAW"

    @classmethod
    def _missing_(cls, value: object) -> Self | None:
        """大文字小文字を区別せずに音声フォーマットを解決する。"""
        if isinstance(value, str):
            normalized_value = value.upper()
            for member in cls:
                if member.value == normalized_value:
                    return member
        return None
