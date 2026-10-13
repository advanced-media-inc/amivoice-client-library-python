"""非同期HTTP v2の受付、状態、認識結果の公開モデル"""

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
