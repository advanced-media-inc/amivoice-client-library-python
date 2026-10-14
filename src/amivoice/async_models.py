"""非同期HTTP v2の受付、状態、認識結果の公開モデル"""

import re
from dataclasses import dataclass
from typing import Literal

from .models import RecognitionResult

__all__ = ["AsyncJobSnapshot", "AsyncJobStatus", "AsyncJobSubmission", "AsyncRecognitionResult"]

AsyncJobStatus = Literal["queued", "started", "processing", "completed", "error"]


@dataclass(frozen=True)
class AsyncJobSubmission:
    """受付済みのジョブIDと元の応答"""

    session_id: str
    raw: str
    data: dict[str, object]


@dataclass(frozen=True)
class AsyncRecognitionResult(RecognitionResult):
    """全体結果と発話区間、resultsは区間内の発話結果を順に並べる"""

    segments: tuple[RecognitionResult, ...] = ()


@dataclass(frozen=True)
class AsyncJobSnapshot:
    """ジョブの観測時点の状態、未到着の任意フィールドはNone"""

    session_id: str
    status: AsyncJobStatus
    raw: str
    data: dict[str, object]
    service_id: str | None = None
    content_id: str | None = None
    audio_size: int | None = None
    audio_md5: str | None = None
    error_message: str | None = None
    recognition: AsyncRecognitionResult | None = None

    @property
    def error_code(self) -> str | None:
        """ジョブのamineth_code又は認識結果の失敗コードを取得する

        Returns:
            str | None: 単一の原因コード、成功又は解析不能の場合はNone
        """
        if self.status == "error":
            codes = re.findall(r"\bamineth_code='([^']*)'", self.error_message or "")
            return codes[0] if len(codes) == 1 and len(codes[0]) == 1 else None
        if self.recognition is not None and self.recognition.is_error:
            code = self.recognition.data.get("code")
            return code if isinstance(code, str) and len(code) == 1 else None
        return None

    @property
    def is_retryable(self) -> bool | None:
        """公式のerror状態の再試行案内に沿った目安を返す

        Trueは待ってからの再登録を検討する目安であり、自動再送の指示ではない
        コードoの拒否は再試行不可、未知の原因は断定しない

        Returns:
            bool | None: 再試行の目安、判断できない場合はNone
        """
        code = self.error_code
        if code == "o":
            return False
        if self.status == "error" and code is not None:
            return True
        return None

    @property
    def is_terminal(self) -> bool:
        """ジョブの終端状態か判定する

        Returns:
            bool: completed又はerrorの場合はTrue
        """
        return self.status in ("completed", "error")

    @property
    def is_error(self) -> bool:
        """ジョブ失敗と認識失敗を判定する

        Returns:
            bool: ジョブ又は認識が失敗した場合はTrue
        """
        return self.status == "error" or (self.recognition is not None and self.recognition.is_error)
