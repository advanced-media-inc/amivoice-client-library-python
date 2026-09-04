# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

"""SegmenterProperties のユニットテスト。"""

from dataclasses import FrozenInstanceError

import pytest

from amivoice._segmenter import SegmenterProperties
from amivoice.exceptions import ConfigurationError


def test_segmenter_properties_single_value_valid_return_parameter() -> None:
    """単一の発話検出設定をパラメータ文字列へ変換できることを確認する。"""
    # Given: threshold のみを指定した SegmenterProperties
    properties = SegmenterProperties(threshold=5000)

    # When: to_parameter を呼び出す
    parameter = properties.to_parameter()

    # Then: 対応する segmenterProperties 文字列が返る
    assert parameter == "threshold=5000"


def test_segmenter_properties_all_values_valid_return_fixed_order() -> None:
    """全設定が定義順のパラメータ文字列へ変換されることを確認する。"""
    # Given: 発話検出、話者ダイアライゼーション、言語識別の設定
    properties = SegmenterProperties(
        threshold=5000,
        pre_time=100,
        post_time=550,
        pre_forced_time=50,
        post_forced_time=100,
        power_threshold=200,
        decay_time=300,
        speaker_diarization=True,
        diarizer_alpha=1e-20,
        diarizer_transition_bias="1e-10",
        languages=("ja", "en"),
    )

    # When: to_parameter を呼び出す
    parameter = properties.to_parameter()

    # Then: フィールド定義順と値の表記が維持される
    assert parameter == (
        "threshold=5000 preTime=100 postTime=550 preForcedTime=50 postForcedTime=100 "
        "powerThreshold=200 decayTime=300 useDiarizer=1 diarizerAlpha=1e-20 "
        "diarizerTransitionBias=1e-10 useLid=ja,en"
    )


def test_segmenter_properties_speaker_diarization_true_valid_return_enabled_flag() -> None:
    """話者ダイアライゼーション有効時に useDiarizer=1 になることを確認する。"""
    # Given: 話者ダイアライゼーションを有効にした設定
    properties = SegmenterProperties(speaker_diarization=True)

    # When: to_parameter を呼び出す
    parameter = properties.to_parameter()

    # Then: 有効化パラメータが返る
    assert parameter == "useDiarizer=1"


def test_segmenter_properties_speaker_diarization_false_valid_return_disabled_flag() -> None:
    """話者ダイアライゼーション無効時に useDiarizer=0 になることを確認する。"""
    # Given: 話者ダイアライゼーションを無効にした設定
    properties = SegmenterProperties(speaker_diarization=False)

    # When: to_parameter を呼び出す
    parameter = properties.to_parameter()

    # Then: 無効化パラメータが返る
    assert parameter == "useDiarizer=0"


def test_segmenter_properties_languages_valid_return_use_lid_parameter() -> None:
    """指定した言語の順序で useLid パラメータが生成されることを確認する。"""
    # Given: 日本語と英語を指定した言語識別設定
    properties = SegmenterProperties(languages=("ja", "en"))

    # When: to_parameter を呼び出す
    parameter = properties.to_parameter()

    # Then: useLid に言語がカンマ区切りで設定される
    assert parameter == "useLid=ja,en"


@pytest.mark.parametrize("languages", [("de",), ("ja", "de")])
def test_segmenter_properties_unsupported_language_invalid_raise_ConfigurationError(
    languages: tuple[str, ...],
) -> None:
    """未対応言語を指定すると ConfigurationError が送出されることを確認する。"""
    # Given: 対応外言語を含む設定
    # When / Then: SegmenterProperties を生成すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError):
        SegmenterProperties(languages=languages)


def test_segmenter_properties_empty_languages_invalid_raise_ConfigurationError() -> None:
    """空の言語タプルを指定すると ConfigurationError が送出されることを確認する。"""
    # Given: 空の languages
    # When / Then: SegmenterProperties を生成すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError):
        SegmenterProperties(languages=())


def test_segmenter_properties_pre_time_not_multiple_invalid_raise_ConfigurationError() -> None:
    """pre_time が 50 の倍数でない場合に ConfigurationError が送出されることを確認する。"""
    # Given: 50 の倍数でない pre_time
    # When / Then: SegmenterProperties を生成すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError):
        SegmenterProperties(pre_time=120)


@pytest.mark.parametrize(
    "field",
    ["threshold", "post_time", "pre_forced_time", "post_forced_time", "power_threshold", "decay_time"],
)
def test_segmenter_properties_negative_value_invalid_raise_ConfigurationError(field: str) -> None:
    """発話検出の数値設定が負の場合に ConfigurationError が送出されることを確認する。"""
    # Given: 負の発話検出設定
    # When / Then: SegmenterProperties を生成すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError):
        SegmenterProperties(**{field: -1})


@pytest.mark.parametrize("speaker_diarization", [None, False])
def test_segmenter_properties_diarizer_tuning_without_enabled_invalid_raise_ConfigurationError(
    speaker_diarization: bool | None,
) -> None:
    """話者ダイアライゼーション無効時の調整値指定で ConfigurationError が送出されることを確認する。"""
    # Given: 話者ダイアライゼーションが有効でない設定と調整値
    # When / Then: SegmenterProperties を生成すると ConfigurationError が送出される
    with pytest.raises(ConfigurationError):
        SegmenterProperties(speaker_diarization=speaker_diarization, diarizer_alpha=1e-20)


def test_segmenter_properties_frozen_field_invalid_raise_FrozenInstanceError() -> None:
    """SegmenterProperties がイミュータブルであることを確認する。"""
    # Given: SegmenterProperties インスタンス
    properties = SegmenterProperties(threshold=5000)

    # When / Then: フィールドに代入すると FrozenInstanceError が送出される
    with pytest.raises(FrozenInstanceError):
        properties.threshold = 1000  # type: ignore[misc]
