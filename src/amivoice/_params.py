"""認識パラメータの集約データクラス。

``AmiVoiceClient`` のコンストラクタ既定値と、``transcribe()`` / ``stream()`` 呼び出し時の
override を一元管理する。呼び出し時 override は :func:`merge_params` で解決する。
"""

import math
from dataclasses import dataclass, replace
from typing import Final

from ._billing import resolve_billing_extension
from .exceptions import ConfigurationError


class _UnsetType:
    """キーワード引数未指定を表す内部 sentinel。"""


UNSET: Final = _UnsetType()

_PROCESSING_TIME_FIELDS: Final[tuple[str, ...]] = (
    "complete_timeout",
    "max_decoding_time",
    "max_response_time",
    "target_response_time",
)
_PROCESSING_RATE_FIELDS: Final[tuple[str, ...]] = (
    "max_decoding_rate",
    "target_decoding_rate",
)


@dataclass(frozen=True)
class RecognitionParams:
    """AmiVoice の認識接続パラメータ一式。

    HRP（HTTP）と WRP（WebSocket）で共通のパラメータに加え、各プロトコル専用の
    パラメータを保持する。専用パラメータは対応しないプロトコルでは無視される。
    """

    # 共通パラメータ
    grammar_file_names: str | None = None
    codec: str | None = None
    result_type: str | None = None
    proxy_server_name: str | None = None
    connect_timeout: int = 0
    receive_timeout: int = 0
    mode: str | None = None
    profile_id: str | None = None
    profile_words: str | None = None
    segmenter_type: str | None = None
    segmenter_properties: str | None = None
    confidence_level: float | None = None
    keep_filler_token: bool | None = None
    result_updated_interval: int | None = None
    extension: str | None = None
    billing_key: str | None = None
    recognition_timeout: int | None = None
    complete_timeout: int | None = None
    wildcard_model_penalty: float | None = None
    max_decoding_time: int | None = None
    max_response_time: int | None = None
    max_decoding_rate: float | None = None
    target_response_time: int | None = None
    target_decoding_rate: float | None = None
    # HRP 専用
    result_encoding: str | None = None
    voice_detection: str | None = None
    accept_topic: str | None = None
    content_type: str | None = None
    accept: str | None = None
    domain_id: str | None = None
    # WRP 専用
    no_input_timeout: int | None = None

    def __post_init__(self) -> None:
        """認識パラメータの入力値を検証する"""
        resolve_billing_extension(self.extension, self.billing_key)
        value = self.confidence_level
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= value <= 1.0):
            raise ConfigurationError("Invalid confidence_level: must be a number between 0.0 and 1.0")

        for field_name in _PROCESSING_TIME_FIELDS:
            _validate_processing_time(field_name, getattr(self, field_name))
        for field_name in _PROCESSING_RATE_FIELDS:
            _validate_processing_rate(field_name, getattr(self, field_name))
        _validate_wildcard_model_penalty(self.wildcard_model_penalty)


def _validate_processing_time(field_name: str, value: int | None) -> None:
    """処理時間制御パラメータの非負整数を検証する

    Args:
        field_name: 検証対象フィールド名
        value: 検証対象の値

    Raises:
        ConfigurationError: 値が非負整数でない場合
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"Invalid {field_name}: must be a non-negative integer")


def _validate_processing_rate(field_name: str, value: float | None) -> None:
    """処理時間制御パラメータのレート値を検証する

    Args:
        field_name: 検証対象フィールド名
        value: 検証対象の値

    Raises:
        ConfigurationError: 値が有限数でない場合、または bool の場合
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"Invalid {field_name}: must be a finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigurationError(f"Invalid {field_name}: must be a finite number")


def _validate_wildcard_model_penalty(value: float | None) -> None:
    """ワイルドカードモデルペナルティの非負値を検証する

    Args:
        value: ワイルドカードモデルペナルティ

    Raises:
        ConfigurationError: 値が非負の有限数でない場合
    """
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError("Invalid wildcard_model_penalty: must be a non-negative finite number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigurationError("Invalid wildcard_model_penalty: must be a non-negative finite number")
    if value < 0:
        raise ConfigurationError("Invalid wildcard_model_penalty: must be a non-negative finite number")


def merge_params(base: RecognitionParams, **overrides: object) -> RecognitionParams:
    """呼び出し時 override を ``base`` にマージした新しい ``RecognitionParams`` を返す。

    値が :data:`UNSET` のキーは ``base`` の値を維持する。それ以外のキーは override で置き換える。

    Args:
        base: 既定となるパラメータ（通常はインスタンス保持の設定）。
        **overrides: フィールド名をキーとした呼び出し時 override。``UNSET`` は無視される。

    Returns:
        マージ済みの ``RecognitionParams``。
    """
    changes = {key: value for key, value in overrides.items() if not isinstance(value, _UnsetType)}
    return replace(base, **changes)
