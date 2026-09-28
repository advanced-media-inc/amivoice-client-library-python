"""音声フォーマット名と接続エンジン名の定数。"""

from enum import StrEnum
from typing import Self

__all__ = ["Codec", "Engine"]


class Codec(StrEnum):
    """AmiVoice APIで指定できる音声フォーマット名

    値は大文字小文字を区別せずに解決する（例: ``Codec("lsb16k")`` は
    ``Codec.LSB16K``）

    文字列が有効な音声フォーマット名かを判定するときは、``"lsb16k" in Codec``
    を使わず、``Codec(value)`` を呼んで ``ValueError`` を捕捉すること。
    ``in`` 演算子の結果はPythonの版で異なる（3.11は ``TypeError``、3.12は
    ``_missing_`` を経由して ``True``、3.13以降は大文字小文字を区別して ``False``）
    """

    # ヘッダあり音声（WAV、Ogg、MP3、FLACなど）用の指定
    # 8kHz・11.025kHzはHEADER_8K、16kHz以上はHEADER_16Kを使う
    HEADER_8K = "8K"
    HEADER_16K = "16K"

    # ヘッダなし音声（生のPCM、mu-law、A-law）用の指定
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


class Engine(StrEnum):
    """AmiVoice APIで指定できる接続エンジン名

    定数名は、公式ドキュメントの「接続エンジン名」から先頭の ``-`` を除き、
    ``-`` を ``_`` に置き換えて大文字にしたもの（例: ``-a2-ja-general`` は
    ``A2_JA_GENERAL``）

    公式ドキュメントの文字列から定数名を一意に導けるようにするため、別名は
    定義しない。各定数のdocstringには公式のエンジン名を記載する

    分類と並び順は、公式ドキュメントの音声認識エンジン一覧に従う
    https://docs.amivoice.com/amivoice-api/manual/engines#list

    ``StrEnum`` のため各定数は ``str`` として扱える。接続エンジン名を受け取る
    引数の型は ``str`` なので、ここにないAmiVoice API Privateの独自エンジン名も
    文字列で指定できる

    文字列が定義済みの接続エンジン名かを判定するときは、``value in Engine`` を
    使わず、``Engine(value)`` を呼んで ``ValueError`` を捕捉すること。
    Python 3.11では ``in`` 演算子に文字列を渡すと ``TypeError`` になる
    """

    # End to End エンジン
    A2_JA_GENERAL = "-a2-ja-general"
    """日本語E2E_汎用"""
    A2_ZH_GENERAL = "-a2-zh-general"
    """中国語E2E_汎用"""
    A2_MULTI_GENERAL = "-a2-multi-general"
    """多言語E2E_汎用"""
    A2B_JA_GENERAL = "-a2b-ja-general"
    """日本語E2E_汎用バッチ"""
    A2B_ZH_GENERAL = "-a2b-zh-general"
    """中国語E2E_汎用バッチ"""
    A2B_MULTI_GENERAL = "-a2b-multi-general"
    """多言語E2E_汎用バッチ"""

    # ハイブリッドエンジン
    A_GENERAL = "-a-general"
    """会話_汎用"""
    A_MEDICAL = "-a-medical"
    """会話_医療"""
    A_BIZFINANCE = "-a-bizfinance"
    """会話_金融"""
    A_BIZINSURANCE = "-a-bizinsurance"
    """会話_保険"""
    A_GENERAL_INPUT = "-a-general-input"
    """音声入力_汎用"""
    A_MEDICAL_INPUT = "-a-medical-input"
    """音声入力_医療"""
    A_BIZINSURANCE_INPUT = "-a-bizinsurance-input"
    """音声入力_保険"""
    A_BIZFINANCE_INPUT = "-a-bizfinance-input"
    """音声入力_金融"""
    A_GENERAL_EN = "-a-general-en"
    """英語_汎用"""
    A_GENERAL_ZH = "-a-general-zh"
    """中国語_汎用"""
    A_GENERAL_KO = "-a-general-ko"
    """韓国語_汎用"""
    A_NAME_INPUT_PRIVATE = "-a-name-input-private"
    """音声入力_氏名（AmiVoice API Private専用、非同期HTTPでは利用不可）"""
    A_ADDRESS_INPUT_PRIVATE = "-a-address-input-private"
    """音声入力_住所（AmiVoice API Private専用、非同期HTTPでは利用不可）"""
    A_RULE_INPUT_PRIVATE = "-a-rule-input-private"
    """音声入力_ルール（AmiVoice API Private専用、非同期HTTPでは利用不可）"""
