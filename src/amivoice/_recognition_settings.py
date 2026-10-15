"""型付き設定と呼び出し時の上書きを認識設定へ変換する"""

from collections.abc import Sequence
from dataclasses import fields
from urllib.parse import urlsplit

from ._params import RecognitionParams, merge_params
from ._segmenter import SegmenterProperties
from .dictionary import ProfileWord, build_profile_words
from .exceptions import ConfigurationError
from .settings import USE_CLIENT_DEFAULT, UseClientDefault


def _validate_custom_url_logging_opt_out(url: str, nolog_url: str) -> None:
    """``logging_opt_out`` が有効なときにカスタム URL がログ保存なしのパスか検証する

    カスタム URL はホスト名を保ったまま使うため、PrivateLink などのホスト名は許容し、
    パスだけをログ保存なしのエンドポイントと比較する

    Args:
        url (str): 検証するカスタム URL
        nolog_url (str): 比較対象のログ保存なしの既定エンドポイント URL

    Raises:
        ConfigurationError: カスタム URL のパスがログ保存なしのエンドポイントと一致しない場合
    """
    nolog_path = urlsplit(nolog_url).path
    if not isinstance(url, str) or urlsplit(url).path != nolog_path:
        raise ConfigurationError(f"Custom URL must use the '{nolog_path}' path when logging_opt_out is True")


def _validate_logging_opt_out(logging_opt_out: object) -> bool:
    """``logging_opt_out`` が bool であることを検証する

    ``None`` や文字列を False または True として解釈すると、意図せずログが保存されるため拒否する

    Args:
        logging_opt_out (object): 検証する ``logging_opt_out`` の値

    Returns:
        bool: 検証済みの ``logging_opt_out``

    Raises:
        ConfigurationError: ``logging_opt_out`` が bool でない場合
    """
    if not isinstance(logging_opt_out, bool):
        raise ConfigurationError("Invalid logging_opt_out: must be a boolean")
    return logging_opt_out


def _resolve_logging_opt_out(override: bool | UseClientDefault, configured: bool) -> bool:
    """呼び出し時の ``logging_opt_out`` override とコンストラクタ設定から最終値を解決する

    Args:
        override (bool | UseClientDefault): 呼び出し時の override``USE_CLIENT_DEFAULT`` は未指定を表す
        configured (bool): コンストラクタで設定された値

    Returns:
        bool: 解決した ``logging_opt_out``

    Raises:
        ConfigurationError: override が bool でも ``USE_CLIENT_DEFAULT`` でもない場合
    """
    if isinstance(override, UseClientDefault):
        return configured
    return _validate_logging_opt_out(override)


def _validate_endpoint_url_type(url: object, parameter_name: str) -> None:
    """明示されたエンドポイント URL が文字列であることを検証する

    URL を明示する利用者は接続先を選んでいるため、``None`` を既定 URL へ置き換えずに拒否する

    Args:
        url (object): 検証する URL``USE_CLIENT_DEFAULT`` は未指定を表す
        parameter_name (str): エラーメッセージに表示する引数名

    Raises:
        ConfigurationError: URL が ``USE_CLIENT_DEFAULT`` でも文字列でもない場合
    """
    if not isinstance(url, (str, UseClientDefault)):
        raise ConfigurationError(f"Invalid {parameter_name}: must be a string")


def _resolve_endpoint_url(
    override: str | UseClientDefault,
    configured_url: str,
    configured_url_is_default: bool,
    nolog_url: str,
    logging_opt_out: bool,
) -> str:
    """URL override とログ保存なし設定から最終エンドポイントを解決する

    既定 URL だけを nolog エンドポイントへ切り替えるカスタム URL は書き換えず、
    ``logging_opt_out`` が有効な場合はログ保存なしのパスであることを検証する

    Args:
        override (str | UseClientDefault): 呼び出し時の URL override``USE_CLIENT_DEFAULT`` は未指定を表す
        configured_url (str): コンストラクタで設定された URL
        configured_url_is_default (bool): コンストラクタで URL を省略したかどうか
            明示的に既定 URL と同じ値を指定した場合との区別に使用する
        nolog_url (str): ログ保存なしの既定エンドポイント URL
        logging_opt_out (bool): ログ保存なしのエンドポイントを使用するかどうか

    Returns:
        str: 解決されたエンドポイント URL

    Raises:
        ConfigurationError: override が文字列でも ``USE_CLIENT_DEFAULT`` でもない場合、または
            ``logging_opt_out`` が有効でカスタム URL がログ保存なしのパスでない場合
    """
    _validate_endpoint_url_type(override, "api_url")
    if isinstance(override, UseClientDefault) and configured_url_is_default:
        return nolog_url if logging_opt_out else configured_url
    url = configured_url if isinstance(override, UseClientDefault) else override
    if logging_opt_out:
        _validate_custom_url_logging_opt_out(url, nolog_url)
    return url


def _resolve_profile_words(profile_words: str | Sequence[ProfileWord] | None) -> str | None:
    """ProfileWord シーケンスまたは既存の文字列を profileWords 文字列へ解決する

    空の ProfileWord シーケンスは ``setProfileWords("")`` で空のパラメータを送らないよう None として扱う

    Args:
        profile_words (str | Sequence[ProfileWord] | None): 既存の wire format 文字列またはシリアライズする ProfileWord シーケンス

    Returns:
        str | None: トランスポートへ渡す profileWords 文字列、空のシーケンスの場合は None
    """
    if profile_words is None or isinstance(profile_words, str):
        return profile_words
    if len(profile_words) == 0:
        return None
    return build_profile_words(profile_words)


def _resolve_profile_words_override(
    profile_words: str | Sequence[ProfileWord] | None | UseClientDefault,
) -> str | None | UseClientDefault:
    """呼び出し時 profile_words override を解決し、未指定 sentinel を保持する

    Args:
        profile_words (str | Sequence[ProfileWord] | None | UseClientDefault): 呼び出し時の profile_words override

    Returns:
        str | None | UseClientDefault: 解決した profileWords 文字列、``None``、または未指定 sentinel
    """
    if isinstance(profile_words, UseClientDefault):
        return profile_words
    return _resolve_profile_words(profile_words)


def _build_selected_channel_properties(selected_channel: int | tuple[int, int]) -> str:
    """チャネル指定をaudioFilterPropertiesのselectedChannel形式へ変換する

    Args:
        selected_channel: 単一チャネル番号または混合する開始・終了チャネル番号

    Returns:
        ``audioFilterProperties``へ渡すselectedChannel文字列

    Raises:
        ConfigurationError: チャネル番号または範囲が不正な場合、範囲の開始と終了が同じ場合
    """
    if isinstance(selected_channel, bool):
        raise ConfigurationError("selected_channel must be a non-negative integer or a pair of integers")
    if isinstance(selected_channel, int):
        if selected_channel < 0:
            raise ConfigurationError("selected_channel must be non-negative")
        return f"selectedChannel={selected_channel}"
    if not isinstance(selected_channel, tuple) or len(selected_channel) != 2:
        raise ConfigurationError("selected_channel must be a non-negative integer or a pair of integers")

    start_channel, end_channel = selected_channel
    if (
        isinstance(start_channel, bool)
        or isinstance(end_channel, bool)
        or not isinstance(start_channel, int)
        or not isinstance(end_channel, int)
        or start_channel < 0
        or end_channel < 0
    ):
        raise ConfigurationError("selected_channel range must contain non-negative integers")
    if start_channel != 0:
        raise ConfigurationError("selected_channel range must start at 0")
    if start_channel > end_channel:
        raise ConfigurationError("selected_channel range start must not be greater than end")
    if start_channel == end_channel:
        raise ConfigurationError(
            "selected_channel range start and end must be different; use an integer to select a single channel"
        )
    return f"selectedChannel={start_channel}-{end_channel}"


def _resolve_audio_filter_properties(
    selected_channel: int | tuple[int, int] | None,
    audio_filter_properties: str | None,
) -> str | None:
    """型付きチャネル指定またはraw音声フィルタプロパティを解決する

    Args:
        selected_channel: 型付きの単一チャネルまたは混合チャネル範囲
        audio_filter_properties: 既存の音声フィルタプロパティ文字列

    Returns:
        トランスポートへ渡す音声フィルタプロパティ文字列

    Raises:
        ConfigurationError: 型付き指定とraw文字列を同時指定した場合
    """
    if selected_channel is not None and audio_filter_properties is not None:
        raise ConfigurationError("selected_channel and audio_filter_properties cannot be specified together")
    return _build_selected_channel_properties(selected_channel) if selected_channel is not None else audio_filter_properties


def _resolve_audio_filter_properties_override(
    selected_channel: int | tuple[int, int] | None | UseClientDefault,
    audio_filter_properties: str | None | UseClientDefault,
) -> str | None | UseClientDefault:
    """呼び出し時の音声フィルタプロパティoverrideを解決する

    Args:
        selected_channel: 型付きチャネル指定または未指定sentinel
        audio_filter_properties: raw文字列指定または未指定sentinel

    Returns:
        トランスポートへ渡す音声フィルタプロパティまたは未指定sentinel

    Raises:
        ConfigurationError: 型付き指定とraw文字列を同時指定した場合
    """
    if not isinstance(selected_channel, UseClientDefault) and not isinstance(audio_filter_properties, UseClientDefault):
        raise ConfigurationError("selected_channel and audio_filter_properties cannot be specified together")
    if isinstance(selected_channel, UseClientDefault):
        return audio_filter_properties
    return _build_selected_channel_properties(selected_channel) if selected_channel is not None else None


def _resolve_segmenter_properties(
    segmenter: SegmenterProperties | None,
    segmenter_properties: str | None,
) -> str | None:
    """コンストラクタの型付き設定または生文字列を解決する

    Args:
        segmenter: 型付きセグメンター設定
        segmenter_properties: 既存の生文字列設定

    Returns:
        トランスポートへ渡すセグメンター設定文字列

    Raises:
        ConfigurationError: 両方の設定が指定された場合
    """
    if segmenter is not None and segmenter_properties is not None:
        raise ConfigurationError("segmenter and segmenter_properties cannot be specified together")
    return segmenter.to_parameter() if segmenter is not None else segmenter_properties


def _resolve_segmenter_override(
    segmenter: SegmenterProperties | None | UseClientDefault,
    segmenter_properties: str | None | UseClientDefault,
) -> str | None | UseClientDefault:
    """呼び出し時の型付き segmenter override と生文字列を解決する

    Args:
        segmenter: 型付きセグメンター設定または未指定 sentinel
        segmenter_properties: 既存の生文字列設定または未指定 sentinel

    Returns:
        トランスポートへ渡すセグメンター設定文字列または未指定 sentinel

    Raises:
        ConfigurationError: 両方の設定が指定された場合
    """
    if not isinstance(segmenter, UseClientDefault) and not isinstance(segmenter_properties, UseClientDefault):
        raise ConfigurationError("segmenter and segmenter_properties cannot be specified together")
    if isinstance(segmenter, UseClientDefault):
        return segmenter_properties
    return segmenter.to_parameter() if segmenter is not None else None


def resolve_recognition_overrides(base: RecognitionParams, supplied: dict[str, object]) -> RecognitionParams:
    """未指定を保持し、補助引数を公式パラメータへ変換する

    Args:
        base (RecognitionParams): クライアント既定値
        supplied (dict[str, object]): 公開メソッドの呼び出し引数

    Returns:
        RecognitionParams: 呼び出し専用の設定
    """
    changes = {field.name: supplied.get(field.name, USE_CLIENT_DEFAULT) for field in fields(base)}
    changes["profile_words"] = _resolve_profile_words_override(supplied.get("profile_words", USE_CLIENT_DEFAULT))
    changes["segmenter_properties"] = _resolve_segmenter_override(
        supplied.get("segmenter", USE_CLIENT_DEFAULT), supplied.get("segmenter_properties", USE_CLIENT_DEFAULT)
    )
    changes["audio_filter_properties"] = _resolve_audio_filter_properties_override(
        supplied.get("selected_channel", USE_CLIENT_DEFAULT), supplied.get("audio_filter_properties", USE_CLIENT_DEFAULT)
    )
    return merge_params(base, **changes)
