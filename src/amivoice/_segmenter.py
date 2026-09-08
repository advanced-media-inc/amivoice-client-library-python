"""segmenterProperties を型付き設定へ変換するモデル。"""

import math
from dataclasses import dataclass
from typing import Final

from .exceptions import ConfigurationError

__all__ = ["SegmenterProperties"]

_SUPPORTED_LANGUAGES: Final[frozenset[str]] = frozenset({"ja", "en", "zh", "ko", "th"})
_NON_NEGATIVE_INTEGER_FIELDS: Final[tuple[str, ...]] = (
    "threshold",
    "pre_time",
    "post_time",
    "pre_forced_time",
    "post_forced_time",
    "power_threshold",
    "decay_time",
)


@dataclass(frozen=True)
class SegmenterProperties:
    """発話検出、話者ダイアライゼーション、言語識別の設定。"""

    # 発話検出
    threshold: int | None = None
    pre_time: int | None = None
    post_time: int | None = None
    pre_forced_time: int | None = None
    post_forced_time: int | None = None
    power_threshold: int | None = None
    decay_time: int | None = None
    # 話者ダイアライゼーション
    speaker_diarization: bool | None = None
    diarizer_alpha: int | float | str | None = None
    diarizer_transition_bias: int | float | str | None = None
    # 言語識別
    languages: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        """設定値を検証する。"""
        for field_name in _NON_NEGATIVE_INTEGER_FIELDS:
            value = getattr(self, field_name)
            _validate_non_negative_integer(field_name, value)

        if self.pre_time is not None and self.pre_time % 50 != 0:
            raise ConfigurationError("Invalid segmenter pre_time: must be a multiple of 50")

        if self.speaker_diarization is not None and not isinstance(self.speaker_diarization, bool):
            raise ConfigurationError("Invalid segmenter speaker_diarization: must be a boolean")

        _validate_diarizer_value("diarizer_alpha", self.diarizer_alpha)
        _validate_diarizer_value("diarizer_transition_bias", self.diarizer_transition_bias)
        if self.speaker_diarization is not True and (
            self.diarizer_alpha is not None or self.diarizer_transition_bias is not None
        ):
            raise ConfigurationError("Invalid segmenter diarizer tuning: speaker_diarization must be enabled")

        if self.languages is not None:
            if not self.languages:
                raise ConfigurationError("Invalid segmenter languages: must not be empty")
            unsupported = [language for language in self.languages if language not in _SUPPORTED_LANGUAGES]
            if unsupported:
                raise ConfigurationError(f"Invalid segmenter languages: unsupported language {unsupported[0]}")

    def to_parameter(self) -> str:
        """SegmenterProperties に設定する文字列を生成する。

        Returns:
            固定順で連結した segmenterProperties の値
        """
        parts: list[str] = []
        parameter_values = (
            ("threshold", self.threshold),
            ("preTime", self.pre_time),
            ("postTime", self.post_time),
            ("preForcedTime", self.pre_forced_time),
            ("postForcedTime", self.post_forced_time),
            ("powerThreshold", self.power_threshold),
            ("decayTime", self.decay_time),
        )
        for name, value in parameter_values:
            if value is not None:
                parts.append(f"{name}={value}")

        if self.speaker_diarization is not None:
            parts.append(f"useDiarizer={int(self.speaker_diarization)}")
        if self.diarizer_alpha is not None:
            parts.append(f"diarizerAlpha={_format_diarizer_value(self.diarizer_alpha)}")
        if self.diarizer_transition_bias is not None:
            parts.append(f"diarizerTransitionBias={_format_diarizer_value(self.diarizer_transition_bias)}")
        if self.languages is not None:
            parts.append(f"useLid={','.join(self.languages)}")

        return " ".join(parts)


def _validate_non_negative_integer(field_name: str, value: int | None) -> None:
    """発話検出用の非負整数を検証する。

    Args:
        field_name: 検証対象フィールド名
        value: 検証対象の値

    Raises:
        ConfigurationError: 値が整数でない場合、または負の場合
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"Invalid segmenter {field_name}: must be a non-negative integer")


def _validate_diarizer_value(field_name: str, value: int | float | str | None) -> None:
    """話者ダイアライゼーション調整値が有限の数値であることを検証する。

    Args:
        field_name: 検証対象フィールド名
        value: 検証対象の値

    Raises:
        ConfigurationError: 値が整数、有限な浮動小数点数、有限な数値文字列のいずれでもない場合
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigurationError(f"Invalid segmenter {field_name}: must be an integer, float, or numeric string")

    if isinstance(value, str):
        try:
            value = float(value)
        except (OverflowError, ValueError):
            raise ConfigurationError(f"Invalid segmenter {field_name}: must be a finite numeric value") from None

    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigurationError(f"Invalid segmenter {field_name}: must be a finite numeric value")


def _format_diarizer_value(value: int | float | str) -> str:
    """話者ダイアライゼーション調整値を文字列化する。

    Args:
        value: 文字列または整数、浮動小数点数の調整値

    Returns:
        指定値を保持した文字列表現
    """
    return value if isinstance(value, str) else repr(value)
