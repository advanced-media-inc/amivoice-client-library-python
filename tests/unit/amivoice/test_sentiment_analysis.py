"""感情パラメータ定義取得APIのテスト"""

import json
from unittest.mock import MagicMock

import pytest

from amivoice import SentimentAnalysisApiError, SentimentAnalysisClient, SentimentParameterDefinition
from amivoice._async_models import parse_job
from amivoice.exceptions import ConfigurationError, ConnectionFailedError

from .test_async_sentiment_models import job_with_sentiment


def _response() -> dict[str, object]:
    return {
        "sentiment_analysis": {
            "result_parameters": {
                "display_language": "ja",
                "definitions": [{"name": "value", "display_name": "表示名", "minimum": 0, "maximum": 1}],
            }
        }
    }


def test_list_parameters_official_response_valid_return_definitions() -> None:
    """公式のJSON構造を型付きの定義へ変換する"""
    # Given: 公式レスポンス構造
    transport = MagicMock()
    transport.request.return_value = (200, json.dumps(_response()).encode())
    client = SentimentAnalysisClient(api_key="dummy", transport=transport)
    # When: パラメータ定義を取得する
    result = client.list_parameters()
    # Then: 正しいホストとパス、Bearer認証を使う
    assert result == (SentimentParameterDefinition("value", "表示名", 0.0, 1.0),)
    assert transport.request.call_args.args == (
        "GET",
        "https://acp-dsrpp.amivoice.com/v2/sentiment-analysis/ja/result-parameters.json",
        {"Authorization": "Bearer dummy"},
        None,
    )


@pytest.mark.parametrize("language", ["en", "ja?u=dummy", "", None])
def test_list_parameters_unsupported_language_invalid_raise_ConfigurationError(language: object) -> None:
    """ja以外を推測でAPIに送らない"""
    # Given: 対応外の言語
    transport = MagicMock()
    client = SentimentAnalysisClient(api_key="dummy", transport=transport)
    # When / Then: 接続前に拒否する
    with pytest.raises(ConfigurationError):
        client.list_parameters(language=language)
    transport.request.assert_not_called()


@pytest.mark.parametrize("status", [400, 401, 404, 500])
def test_list_parameters_http_error_invalid_raise_SentimentAnalysisApiError(status: int) -> None:
    """HTTPエラーと元の本文を保持する"""
    # Given: JSON形式のエラー応答
    transport = MagicMock()
    body = b'{"message":"No authorization header"}'
    transport.request.return_value = (status, body)
    client = SentimentAnalysisClient(api_key="dummy", transport=transport)
    # When / Then: 専用例外に診断情報を保持する
    with pytest.raises(SentimentAnalysisApiError) as caught:
        client.list_parameters()
    assert caught.value.status_code == status
    assert caught.value.raw_body == body


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"\xff",
        b"{}",
        b'{"sentiment_analysis":[]}',
        b'{"sentiment_analysis":{"result_parameters":{"definitions":[1]}}}',
        b'{"sentiment_analysis":{"result_parameters":{"definitions":[{"name":"x","display_name":"x","minimum":true,"maximum":1}]}}}',
        b'{"sentiment_analysis":{"result_parameters":{"definitions":[{"name":"x","display_name":"x","minimum":0,"maximum":NaN}]}}}',
    ],
)
def test_list_parameters_malformed_response_invalid_raise_SentimentAnalysisApiError(body: bytes) -> None:
    """不正な型や非有限数を成功扱いしない"""
    # Given: 不正な成功レスポンス
    transport = MagicMock()
    transport.request.return_value = (200, body)
    client = SentimentAnalysisClient(api_key="dummy", transport=transport)
    # When / Then: JSONの構造を検証する
    with pytest.raises(SentimentAnalysisApiError) as caught:
        client.list_parameters()
    assert caught.value.raw_body == body


def test_list_parameters_network_error_invalid_raise_ConnectionFailedError() -> None:
    """例外の詳細に認証情報が含まれても外へ出さない"""
    # Given: 認証情報を含む通信例外
    transport = MagicMock()
    transport.request.side_effect = OSError("dummy")
    client = SentimentAnalysisClient(api_key="dummy", transport=transport)
    # When / Then: 安全なメッセージだけを返す
    with pytest.raises(ConnectionFailedError) as caught:
        client.list_parameters()
    assert "dummy" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_list_parameters_result_mapping_valid_return_display_metadata() -> None:
    """定義名を区間指標のキーと結び付け、解析時には自動取得しない"""
    # Given: 定義APIの合成応答と未知の整数指標を含む区間
    transport = MagicMock()
    transport.request.return_value = (200, json.dumps(_response()).encode())
    client = SentimentAnalysisClient(api_key="dummy", transport=transport)
    data = job_with_sentiment({"segments": [{"starttime": 0, "endtime": 10, "value": 1}]})
    # When: まず結果を解析し、必要なときだけ定義を取得する
    segment = parse_job(json.dumps(data).encode(), "job1").recognition.sentiment_analysis.segments[0]
    transport.request.assert_not_called()
    definitions = {item.name: item for item in client.list_parameters(language="ja")}
    # Then: 結果の整数値と表示名・範囲を別の責務として参照できる
    assert segment.parameters["value"] == 1
    assert definitions["value"].display_name == "表示名"
    assert definitions["value"].minimum <= segment.parameters["value"] <= definitions["value"].maximum


@pytest.mark.parametrize("base_url", ["http://example.test", "https://dummy@example.test", "https://example.test?u=dummy"])
def test_sentiment_client_base_url_invalid_raise_ConfigurationError(base_url: str) -> None:
    """TLSと安全なURLを要求する"""
    # Given: 不正な接続設定
    # When / Then: 初期化時に拒否する
    with pytest.raises(ConfigurationError):
        SentimentAnalysisClient(api_key="dummy", base_url=base_url)
