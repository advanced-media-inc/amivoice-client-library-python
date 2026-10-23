"""公開設定とクライアント既定値を継承するsentinel"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

from ._segmenter import SegmenterProperties
from .constants import Codec
from .dictionary import ProfileWord
from .exceptions import ConfigurationError


class UseClientDefault(Enum):
    """クライアントに設定した値を継承する指定"""

    USE_CLIENT_DEFAULT = "USE_CLIENT_DEFAULT"

    def __repr__(self) -> str:
        """短い公開名を返す

        Returns:
            str: 公開定数の名前
        """
        return "USE_CLIENT_DEFAULT"


USE_CLIENT_DEFAULT: Final = UseClientDefault.USE_CLIENT_DEFAULT


@dataclass(frozen=True, kw_only=True)
class RecognitionSettings:
    """認識設定の差分、未指定は継承しNoneは任意設定を解除する

    通信先・プロキシ・ソケット待機時間はクライアントの引数で指定する
    インタフェースごとの対応可否と値はクライアント初期化・呼び出し時に検証する

    Args:
        grammar_file_names (str | None | UseClientDefault): 接続エンジン名
        codec (Codec | str | None | UseClientDefault): 音声フォーマット
        profile_id (str | None | UseClientDefault): ユーザー辞書の参照名
        profile_words (str | Sequence[ProfileWord] | None | UseClientDefault): セッションの単語登録
        segmenter (SegmenterProperties | None | UseClientDefault): 型付きの発話検出設定
        segmenter_properties (str | None | UseClientDefault): 発話検出設定の文字列
        selected_channel (int | tuple[int, int] | None | UseClientDefault): 単一チャネル又は0から始まる平均範囲
        audio_filter_properties (str | None | UseClientDefault): 同期HTTPのチャネル指定
        confidence_level (float | None | UseClientDefault): 信頼度しきい値、0から1
        keep_filler_token (bool | None | UseClientDefault): フィラーを残すか
        result_updated_interval (int | None | UseClientDefault): WebSocketの途中結果間隔、ミリ秒
        extension (str | None | UseClientDefault): 使用量集計のJSON設定
        billing_key (str | None | UseClientDefault): 使用量集計タグ
        recognition_timeout (int | None | UseClientDefault): 認識完了のタイムアウト、ミリ秒
        complete_timeout (int | None | UseClientDefault): ルール認識の確定待ち時間、ミリ秒
        wildcard_model_penalty (float | None | UseClientDefault): ルール認識のワイルドカードペナルティ
        max_decoding_time (int | None | UseClientDefault): 最大認識処理時間、ミリ秒
        max_response_time (int | None | UseClientDefault): 最大応答時間、ミリ秒
        max_decoding_rate (float | None | UseClientDefault): 最大の認識時間倍率
        target_response_time (int | None | UseClientDefault): 目標応答時間、ミリ秒
        target_decoding_rate (float | None | UseClientDefault): 目標の認識時間倍率
        no_input_timeout (int | None | UseClientDefault): WebSocketの発話開始待ち時間、ミリ秒
        logging_opt_out (bool | None | UseClientDefault): 音声ログを残さないか、Noneは非同期HTTPのみ送信解除
        content_id (str | None | UseClientDefault): 非同期HTTPのユーザー定義ID、冪等性キーではない
        compatible_with_sync (bool | None | UseClientDefault): 非同期HTTPの同期互換結果形式
        speaker_diarization (bool | None | UseClientDefault): 非同期HTTPの話者ダイアライゼーション
        diarization_min_speaker (int | None | UseClientDefault): 非同期HTTPの最小話者数、1..20
        diarization_max_speaker (int | None | UseClientDefault): 非同期HTTPの最大話者数、1..20
    """

    grammar_file_names: str | None | UseClientDefault = USE_CLIENT_DEFAULT
    codec: Codec | str | None | UseClientDefault = USE_CLIENT_DEFAULT
    profile_id: str | None | UseClientDefault = USE_CLIENT_DEFAULT
    profile_words: str | Sequence[ProfileWord] | None | UseClientDefault = USE_CLIENT_DEFAULT
    segmenter: SegmenterProperties | None | UseClientDefault = USE_CLIENT_DEFAULT
    segmenter_properties: str | None | UseClientDefault = USE_CLIENT_DEFAULT
    selected_channel: int | tuple[int, int] | None | UseClientDefault = USE_CLIENT_DEFAULT
    audio_filter_properties: str | None | UseClientDefault = USE_CLIENT_DEFAULT
    confidence_level: float | None | UseClientDefault = USE_CLIENT_DEFAULT
    keep_filler_token: bool | None | UseClientDefault = USE_CLIENT_DEFAULT
    result_updated_interval: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    extension: str | None | UseClientDefault = USE_CLIENT_DEFAULT
    billing_key: str | None | UseClientDefault = USE_CLIENT_DEFAULT
    recognition_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    complete_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    wildcard_model_penalty: float | None | UseClientDefault = USE_CLIENT_DEFAULT
    max_decoding_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    max_response_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    max_decoding_rate: float | None | UseClientDefault = USE_CLIENT_DEFAULT
    target_response_time: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    target_decoding_rate: float | None | UseClientDefault = USE_CLIENT_DEFAULT
    no_input_timeout: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    logging_opt_out: bool | None | UseClientDefault = USE_CLIENT_DEFAULT
    content_id: str | None | UseClientDefault = USE_CLIENT_DEFAULT
    compatible_with_sync: bool | None | UseClientDefault = USE_CLIENT_DEFAULT
    speaker_diarization: bool | None | UseClientDefault = USE_CLIENT_DEFAULT
    diarization_min_speaker: int | None | UseClientDefault = USE_CLIENT_DEFAULT
    diarization_max_speaker: int | None | UseClientDefault = USE_CLIENT_DEFAULT

    def __post_init__(self) -> None:
        """単語一覧をコピーして呼び出し元からの変更を防ぐ"""
        words = self.profile_words
        if words is not USE_CLIENT_DEFAULT and words is not None and not isinstance(words, str):
            if not isinstance(words, Sequence):
                raise ConfigurationError("profile_words must be a string or a sequence of ProfileWord")
            object.__setattr__(self, "profile_words", tuple(words))
