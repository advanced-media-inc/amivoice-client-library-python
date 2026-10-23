"""非同期HTTP v2の受付、状態、認識結果の公開モデル"""

import re
from dataclasses import dataclass, field
from typing import Literal

from .exceptions import ConfigurationError
from .models import RecognitionResult

__all__ = [
    "AsyncJobSnapshot",
    "AsyncJobStatus",
    "AsyncJobSubmission",
    "AsyncRecognitionResult",
    "SentimentAnalysisResult",
    "SentimentSegment",
]

# 既知状態を補完しつつ、サービスが今後追加する状態も文字列として保持する
AsyncJobStatus = Literal["queued", "started", "processing", "completed", "error"] | str


@dataclass(frozen=True)
class AsyncJobSubmission:
    """受付済みのジョブIDと元の応答"""

    session_id: str
    raw: str
    data: dict[str, object]
    audio_size: int | None = None
    audio_md5: str | None = None

    def matches_audio(self, snapshot: "AsyncJobSnapshot") -> bool | None:
        """受付時の音声サイズとMD5を同じジョブの観測値と照合する

        MD5は転送確認用であり暗号学的な真正性を保証しない
        値が不足する場合はNone、不一致を確認できた場合はFalseを返す

        Args:
            snapshot (AsyncJobSnapshot): 同じジョブの状態

        Returns:
            bool | None: 両方一致ならTrue、不一致ならFalse、未確定ならNone

        Raises:
            ConfigurationError: ジョブIDが異なる場合
        """
        if self.session_id != snapshot.session_id:
            raise ConfigurationError("Audio verification requires the same job ID")
        size_known = self.audio_size is not None and snapshot.audio_size is not None
        md5_known = self.audio_md5 is not None and snapshot.audio_md5 is not None
        if size_known and self.audio_size != snapshot.audio_size:
            return False
        if self.audio_md5 is not None and snapshot.audio_md5 is not None and self.audio_md5.lower() != snapshot.audio_md5.lower():
            return False
        return True if size_known and md5_known else None


@dataclass(frozen=True)
class SentimentSegment:
    """発話区間ごとの感情分析結果

    区間の開始・終了時刻は音声先頭からの相対ミリ秒で表す
    感情指標はparameters辞書やenergy、stressなどのプロパティから参照できる
    応答に含まれない指標のプロパティはNoneを返す
    """

    starttime: int | float
    endtime: int | float
    parameters: dict[str, int]
    raw: str
    data: dict[str, object]

    @property
    def energy(self) -> int | None:
        """エネルギーを取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("energy")

    @property
    def stress(self) -> int | None:
        """ストレスを取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("stress")

    @property
    def emo_cog(self) -> int | None:
        """感情バランス論理を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("emo_cog")

    @property
    def concentration(self) -> int | None:
        """集中を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("concentration")

    @property
    def anticipation(self) -> int | None:
        """期待を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("anticipation")

    @property
    def excitement(self) -> int | None:
        """興奮を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("excitement")

    @property
    def hesitation(self) -> int | None:
        """躊躇を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("hesitation")

    @property
    def uncertainty(self) -> int | None:
        """不確実を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("uncertainty")

    @property
    def intensive_thinking(self) -> int | None:
        """思考を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("intensive_thinking")

    @property
    def imagination_activity(self) -> int | None:
        """想像力を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("imagination_activity")

    @property
    def embarrassment(self) -> int | None:
        """困惑を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("embarrassment")

    @property
    def passionate(self) -> int | None:
        """情熱を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("passionate")

    @property
    def brain_power(self) -> int | None:
        """脳活動を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("brain_power")

    @property
    def confidence(self) -> int | None:
        """自信を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("confidence")

    @property
    def aggression(self) -> int | None:
        """攻撃性憤りを取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("aggression")

    @property
    def atmosphere(self) -> int | None:
        """雰囲気会話傾向を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("atmosphere")

    @property
    def upset(self) -> int | None:
        """動揺を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("upset")

    @property
    def content(self) -> int | None:
        """喜びを取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("content")

    @property
    def dissatisfaction(self) -> int | None:
        """不満を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("dissatisfaction")

    @property
    def extreme_emotion(self) -> int | None:
        """極端な起伏を取得する

        Returns:
            int | None: 現在の指標値、省略時はNone
        """
        return self.parameters.get("extreme_emotion")


@dataclass(frozen=True)
class SentimentAnalysisResult:
    """完了ジョブの感情区間と感情分析内エラー

    解析できない感情結果は元の値をdataに保持し、parse_errorで理由を示す
    サーバーのエラー情報とクライアントでの解析失敗は区別する
    """

    raw: str
    data: object
    segments: tuple[SentimentSegment, ...] = ()
    code: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    parse_error: str | None = field(default=None, kw_only=True)

    @property
    def is_error(self) -> bool:
        """認識本体とは独立して感情分析内のエラーを判定する

        Returns:
            bool: codeが存在するかエラー文字列が非空、又は解析失敗時はTrue
        """
        return self.code is not None or bool(self.error_code) or bool(self.error_message) or self.parse_error is not None


@dataclass(frozen=True)
class AsyncRecognitionResult(RecognitionResult):
    """全体結果と発話区間、resultsは区間内の発話結果を順に並べる"""

    segments: tuple[RecognitionResult, ...] = ()
    sentiment_analysis: SentimentAnalysisResult | None = field(default=None, kw_only=True)


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
