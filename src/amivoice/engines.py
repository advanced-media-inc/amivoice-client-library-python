"""音声コーデックと接続エンジン名の定数。"""

from enum import StrEnum
from typing import Self

__all__ = ["Codec", "Engines"]


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


class Engines:
    """AmiVoice APIで指定できる接続エンジン名。"""

    # End to End エンジン
    A2_JA_GENERAL = "-a2-ja-general"
    A2_ZH_GENERAL = "-a2-zh-general"
    A2_MULTI_GENERAL = "-a2-multi-general"
    A2B_JA_GENERAL = "-a2b-ja-general"
    A2B_ZH_GENERAL = "-a2b-zh-general"
    A2B_MULTI_GENERAL = "-a2b-multi-general"

    # ハイブリッド（会話）エンジン
    A_GENERAL = "-a-general"
    A_MEDICAL = "-a-medical"
    A_BIZFINANCE = "-a-bizfinance"
    A_BIZINSURANCE = "-a-bizinsurance"
    A_GENERAL_EN = "-a-general-en"
    A_GENERAL_ZH = "-a-general-zh"
    A_GENERAL_KO = "-a-general-ko"

    # ハイブリッド（音声入力）エンジン
    A_GENERAL_INPUT = "-a-general-input"
    A_MEDICAL_INPUT = "-a-medical-input"
    A_BIZINSURANCE_INPUT = "-a-bizinsurance-input"
    A_BIZFINANCE_INPUT = "-a-bizfinance-input"

    # AmiVoice API Private エンジン
    A_NAME_INPUT_PRIVATE = "-a-name-input-private"
    A_ADDRESS_INPUT_PRIVATE = "-a-address-input-private"
    A_RULE_INPUT_PRIVATE = "-a-rule-input-private"

    # 読みやすさのためのカテゴリ別別名
    E2E_JA_GENERAL = A2_JA_GENERAL
    E2E_ZH_GENERAL = A2_ZH_GENERAL
    E2E_MULTI_GENERAL = A2_MULTI_GENERAL
    E2E_B_JA_GENERAL = A2B_JA_GENERAL
    E2E_B_ZH_GENERAL = A2B_ZH_GENERAL
    E2E_B_MULTI_GENERAL = A2B_MULTI_GENERAL
    HYBRID_GENERAL = A_GENERAL
    HYBRID_MEDICAL = A_MEDICAL
    HYBRID_BIZFINANCE = A_BIZFINANCE
    HYBRID_BIZINSURANCE = A_BIZINSURANCE
    HYBRID_GENERAL_EN = A_GENERAL_EN
    HYBRID_GENERAL_ZH = A_GENERAL_ZH
    HYBRID_GENERAL_KO = A_GENERAL_KO
    HYBRID_GENERAL_INPUT = A_GENERAL_INPUT
    HYBRID_MEDICAL_INPUT = A_MEDICAL_INPUT
    HYBRID_BIZINSURANCE_INPUT = A_BIZINSURANCE_INPUT
    HYBRID_BIZFINANCE_INPUT = A_BIZFINANCE_INPUT
    PRIVATE_NAME_INPUT = A_NAME_INPUT_PRIVATE
    PRIVATE_ADDRESS_INPUT = A_ADDRESS_INPUT_PRIVATE
    PRIVATE_RULE_INPUT = A_RULE_INPUT_PRIVATE
