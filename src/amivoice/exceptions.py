"""AmiVoice クライアントにおける例外クラス。"""

import json
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .async_models import AsyncJobSnapshot


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


class AsyncHttpApiError(AmiVoiceError):
    """非同期HTTPの受付失敗、HTTPエラー、不正応答"""

    def __init__(
        self, message: str, *, status_code: int | None = None, raw_body: bytes = b"", session_id: str | None = None
    ) -> None:
        """安全な表示メッセージと調査用の本文を保持する

        Args:
            message (str): 認証情報を含めない表示用の説明
            status_code (int | None): HTTPステータス
            raw_body (bytes): 元のレスポンス本文、無条件にログへ出力しない
            session_id (str | None): 取得対象のジョブID
        """
        super().__init__(message)
        self.status_code = status_code
        self.raw_body = raw_body
        self.body = raw_body.decode("utf-8", errors="replace")
        self.response_body = self.body
        self.session_id = session_id
        self.data: dict[str, object] | None = None
        try:
            data = json.loads(raw_body.decode("utf-8"))
            if isinstance(data, dict):
                self.data = data
        except (ValueError, RecursionError):
            pass
        code = self.data.get("code") if self.data is not None else None
        api_message = self.data.get("message") if self.data is not None else None
        self.code = code if isinstance(code, str) else None
        self.api_message = api_message if isinstance(api_message, str) else None


class AsyncHttpAuthenticationError(AsyncHttpApiError, AuthenticationError):
    """非同期HTTPの認証拒否、HTTP詳細を保持して両方の基底例外で捕捉できる"""


class AsyncJobError(RecognitionError):
    """ジョブ又は認識が失敗した終端結果"""

    def __init__(self, message: str, snapshot: "AsyncJobSnapshot") -> None:
        """失敗したジョブ状態を保持する

        Args:
            message (str): 安全なエラー説明
            snapshot (AsyncJobSnapshot): 失敗した状態と認識結果
        """
        super().__init__(message, result=snapshot)
        self.snapshot = snapshot
        self.session_id = snapshot.session_id

    @property
    def error_code(self) -> str | None:
        """スナップショットの原因コードを取得する

        Returns:
            str | None: 原因コード又はNone
        """
        return self.snapshot.error_code

    @property
    def is_retryable(self) -> bool | None:
        """スナップショットの再試行の目安を取得する

        Returns:
            bool | None: 再試行の目安又はNone
        """
        return self.snapshot.is_retryable


class AsyncJobTimeoutError(AmiVoiceError, TimeoutError):
    """クライアントの待機終了、サーバーのジョブはキャンセルしない"""

    def __init__(self, session_id: str, snapshot: "AsyncJobSnapshot | None" = None) -> None:
        """再開に必要なジョブIDと最後の状態を保持する

        Args:
            session_id (str): 再開できるジョブID
            snapshot (AsyncJobSnapshot | None): 最後に取得した状態
        """
        super().__init__("Async HTTP job wait timed out; the server job has not been cancelled")
        self.session_id = session_id
        self.snapshot = snapshot


class ConfigurationError(AmiVoiceError):
    """設定が不正な場合に送出される例外。"""


class ApiKeyIssuanceApiError(AmiVoiceError):
    """API キー発行 API がエラーを返した場合に送出される例外"""

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
            message: 例外メッセージ
            status_code: HTTP ステータスコード
            body: UTF-8 としてデコードしたレスポンス本文
            raw_body: デコード前のレスポンス本文
        """
        super().__init__(message)
        self.status_code: int | None = status_code
        self.body: str | None = body
        self.raw_body: bytes | None = raw_body
        self.response_body: str | None = body


class SentimentAnalysisApiError(AmiVoiceError):
    """感情パラメータ定義APIがエラーや不正な結果を返した場合の例外"""

    def __init__(
        self, message: str, *, status_code: int | None = None, body: str | None = None, raw_body: bytes | None = None
    ) -> None:
        """HTTPステータスと元の本文を保持する

        Args:
            message (str): 安全な例外メッセージ
            status_code (int | None): HTTPステータス
            body (str | None): 表示用のレスポンス本文
            raw_body (bytes | None): デコード前の本文
        """
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.raw_body = raw_body
        self.response_body = body


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
