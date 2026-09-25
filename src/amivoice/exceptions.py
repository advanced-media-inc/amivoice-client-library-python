"""AmiVoice クライアントにおける例外クラス。"""

from typing import Protocol


class RecognitionResultLike(Protocol):
    """``RecognitionError`` に添付される認識結果の Protocol。"""

    @property
    def raw(self) -> str:
        """生レスポンス文字列。

        Returns:
            str: 生のレスポンス文字列
        """
        ...

    @property
    def data(self) -> dict[str, object]:
        """パース済み JSON データ。

        Returns:
            dict[str, object]: パース済みの JSON データ
        """
        ...

    @property
    def is_error(self) -> bool:
        """エラー結果か否か。

        Returns:
            bool: エラー結果の場合は ``True``
        """
        ...

    @property
    def session_id(self) -> str | None:
        """セッション ID。

        Returns:
            str | None: セッション ID。存在しない場合は ``None``
        """
        ...


class AmiVoiceError(Exception):
    """AmiVoice 高レベルクライアントの基底例外クラス。"""

    def __init__(self, message: str) -> None:
        """例外を初期化する。

        Args:
            message (str): 例外メッセージ
        """
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
        """例外を初期化する。

        Args:
            message (str): 例外メッセージ
            result (RecognitionResultLike | None): エラーの原因となった認識結果
        """
        super().__init__(message)
        self.result: RecognitionResultLike | None = result


class ConfigurationError(AmiVoiceError):
    """設定が不正な場合に送出される例外。"""


class DictionaryApiError(AmiVoiceError):
    """ユーザー辞書登録 API がエラーを返した場合に送出される例外"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: str | None = None,
        raw_body: bytes | None = None,
    ) -> None:
        """API エラーの詳細を保持して例外を初期化する

        Args:
            message (str): 例外メッセージ
            status_code (int | None): HTTP ステータスコード
            body (str | None): UTF-8 としてデコードしたレスポンス本文
            raw_body (bytes | None): デコード前のレスポンス本文
        """
        super().__init__(message)
        self.status_code: int | None = status_code
        self.body: str | None = body
        self.raw_body: bytes | None = raw_body
        self.response_body: str | None = body
