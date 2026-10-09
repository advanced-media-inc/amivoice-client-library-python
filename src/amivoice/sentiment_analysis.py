"""感情分析結果に含まれるパラメータの定義一覧を取得するAPI"""

import http.client
import json
import math
import os
from dataclasses import dataclass
from typing import Literal, Protocol

from ._connection_settings import parse_service_url
from ._http_api import HttpApiConnection, validate_service_api_key
from .exceptions import ConfigurationError, ConnectionFailedError, SentimentAnalysisApiError

__all__ = ["SentimentAnalysisClient", "SentimentAnalysisTransport", "SentimentParameterDefinition"]
_DEFAULT_BASE_URL = "https://acp-dsrpp.amivoice.com"


@dataclass(frozen=True)
class SentimentParameterDefinition:
    """公式の感情パラメータ名、表示名、値の範囲"""

    name: str
    display_name: str
    minimum: float
    maximum: float


class SentimentAnalysisTransport(Protocol):
    """感情パラメータAPIのHTTP通信を注入するインタフェース"""

    def request(self, method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, bytes]:
        """HTTPステータスと本文を取得する

        Args:
            method (str): HTTPメソッド
            url (str): 接続先
            headers (dict[str, str]): Bearer認証ヘッダ
            body (bytes | None): 本文、GET時はNone

        Returns:
            tuple[int, bytes]: ステータスと本文
        """
        ...


def _parse_sentiment_definitions(body: bytes) -> tuple[SentimentParameterDefinition, ...]:
    data = json.loads(body.decode("utf-8"))
    parameters = data["sentiment_analysis"]["result_parameters"]
    if not isinstance(parameters, dict) or not isinstance(parameters.get("definitions"), list):
        raise ValueError("definitions must be an array")
    if "display_language" in parameters and not isinstance(parameters["display_language"], str):
        raise ValueError("display_language must be a string")
    result = []
    for item in parameters["definitions"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("display_name"), str):
            raise ValueError("sentiment definition names must be strings")
        limits = []
        for key in ("minimum", "maximum"):
            value = item.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("sentiment definition limits must be finite numbers")
            limits.append(float(value))
        result.append(SentimentParameterDefinition(item["name"], item["display_name"], limits[0], limits[1]))
    return tuple(result)


class SentimentAnalysisClient:
    """感情の定義一覧だけを取得し、音声認識ジョブは作成しない"""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        transport: SentimentAnalysisTransport | None = None,
    ) -> None:
        """認証情報とHTTPS接続先を保持する

        Args:
            api_key (str | None): APIキー、省略時はAMIVOICE_API_KEY
            base_url (str): 感情定義APIのベースURL
            timeout (float): HTTP接続と受信の待機秒数
            transport (SentimentAnalysisTransport | None): テスト用通信処理

        Raises:
            ConfigurationError: 接続先や認証情報が不正な場合
        """
        self._api_key = validate_service_api_key(api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY"))
        parse_service_url(base_url, ("https",))
        self._base_url = base_url.rstrip("/")
        self._transport = transport if transport is not None else HttpApiConnection(timeout)

    def list_parameters(self, *, language: Literal["ja"] = "ja") -> tuple[SentimentParameterDefinition, ...]:
        """jaの感情パラメータ定義を取得する

        Args:
            language (Literal["ja"]): 表示言語、公式に対応するのはjaのみ

        Returns:
            tuple[SentimentParameterDefinition, ...]: 定義一覧

        Raises:
            ConfigurationError: ja以外の言語の場合
            ConnectionFailedError: 通信に失敗した場合
            SentimentAnalysisApiError: HTTPエラー又は不正な応答の場合
        """
        if language != "ja":
            raise ConfigurationError("Sentiment parameter language must be ja")
        url = f"{self._base_url}/v2/sentiment-analysis/{language}/result-parameters.json"
        try:
            status, body = self._transport.request("GET", url, {"Authorization": f"Bearer {self._api_key}"}, None)
        except (OSError, http.client.HTTPException):
            raise ConnectionFailedError("Sentiment analysis API connection failed") from None
        text = body.decode("utf-8", errors="replace")
        if status != 200:
            raise SentimentAnalysisApiError(
                f"Sentiment analysis API request failed with HTTP {status}", status_code=status, body=text, raw_body=body
            )
        try:
            return _parse_sentiment_definitions(body)
        except (UnicodeDecodeError, ValueError, TypeError, KeyError, OverflowError):
            raise SentimentAnalysisApiError(
                "Sentiment analysis API returned an invalid response", status_code=status, body=text, raw_body=body
            ) from None
