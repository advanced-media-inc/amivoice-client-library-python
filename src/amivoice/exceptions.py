"""AmiVoice クライアントにおける例外クラス。"""

from typing import Protocol


class RecognitionResultLike(Protocol):
    """``RecognitionError`` に添付される認識結果の Protocol。"""

    @property
    def raw(self) -> str:
        """生レスポンス文字列。"""
        ...

    @property
    def data(self) -> dict[str, object]:
        """パース済み JSON データ。"""
        ...

    @property
    def is_error(self) -> bool:
        """エラー結果か否か。"""
        ...

    @property
    def session_id(self) -> str | None:
        """セッション ID。"""
        ...


class AmiVoiceError(Exception):
    """AmiVoice 高レベルクライアントの基底例外クラス。"""

    def __init__(self, message: str) -> None:
        """例外を初期化する。"""
        super().__init__(message)
        self.message: str = message

    def __str__(self) -> str:  # noqa: D105
        return self.message


class AuthenticationError(AmiVoiceError):
    """API キーが未設定または無効な場合に送出される例外。"""


class ConnectionFailedError(AmiVoiceError):
    """AmiVoice へのトランスポート接続に失敗した場合に送出される例外。"""


class RecognitionError(AmiVoiceError):
    """音声認識が失敗、またはサービスがエラー結果を返した場合に送出される例外。"""

    def __init__(self, message: str, result: RecognitionResultLike | None = None) -> None:
        """例外を初期化する。"""
        super().__init__(message)
        self.result: RecognitionResultLike | None = result


class ConfigurationError(AmiVoiceError):
    """設定が不正な場合に送出される例外。"""
