"""公式仕様の例外条件を保持する認識設定のテスト"""

import pytest

from amivoice import SegmenterProperties
from amivoice._params import RecognitionParams
from amivoice._request_parameters import build_http_multipart
from amivoice.exceptions import ConfigurationError


def test_segmenter_negative_power_threshold_valid_disable_filter() -> None:
    """0以下で無効になるpowerThresholdを型付き設定でも指定できる"""
    # Given: 無効化する負数
    # When: 型付き設定を作る
    settings = SegmenterProperties(power_threshold=-1)
    # Then: 公式値を変更せず送る
    assert settings.to_parameter() == "powerThreshold=-1"


def test_http_codec_unsupported_invalid_raise_ConfigurationError() -> None:
    """未掲載の音声フォーマットは設定例外として返す"""
    # Given: 不正なフォーマット
    params = RecognitionParams(grammar_file_names="-a-general", codec="unknown")
    # When / Then: リクエストを生成しない
    with pytest.raises(ConfigurationError, match="codec"):
        build_http_multipart(params, b"a")


def test_http_filler_e2e_invalid_raise_ConfigurationError() -> None:
    """E2Eで非対応のフィラー設定を送らない"""
    # Given: E2Eエンジンでフィラー保持を指定
    params = RecognitionParams(grammar_file_names="-a2-ja-general", keep_filler_token=True)
    # When / Then: サポート対象外を明示する
    with pytest.raises(ConfigurationError, match="keep_filler_token"):
        build_http_multipart(params, b"a")
