"""AmiVoice ユーザー辞書登録 API の高レベルクライアント"""

import http.client
import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, NoReturn, Protocol
from urllib.parse import quote, urlsplit

from .exceptions import AuthenticationError, ConfigurationError, ConnectionFailedError, DictionaryApiError

__all__ = ["DictionaryTransport", "ProfileWord", "UserDictionaryClient"]

_DEFAULT_BASE_URL = "https://acp-api.amivoice.com"
SamplingRate = Literal["8k", "16k"]


class DictionaryTransport(Protocol):
    """ユーザー辞書登録 API への HTTP リクエストを実行するトランスポート"""

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        """HTTP レスポンスのステータスコードと本文を返す

        Args:
            method (str): HTTP メソッド
            url (str): リクエスト URL
            headers (dict[str, str]): HTTP リクエストヘッダー
            body (bytes | None): HTTP リクエスト本文

        Returns:
            tuple[int, bytes]: HTTP ステータスコードとレスポンス本文
        """
        ...


@dataclass(frozen=True)
class ProfileWord:
    """ユーザー辞書の単語（ハイブリッド/E2E 両対応）"""

    written: str
    spoken: str | None = None
    classname: str | None = None
    alternative_written: str | None = None
    biasing: float | None = None

    def __post_init__(self) -> None:
        """単語強調度が API の許容範囲に収まることを検証する"""
        if self.biasing is None:
            return
        if isinstance(self.biasing, bool) or not isinstance(self.biasing, (int, float)):
            raise ConfigurationError("biasing must be a number between 0.0 and 1.0")
        normalized_biasing = float(self.biasing)
        if not math.isfinite(normalized_biasing) or not 0.0 <= normalized_biasing <= 1.0:
            raise ConfigurationError("biasing must be a number between 0.0 and 1.0")
        object.__setattr__(self, "biasing", normalized_biasing)

    def to_dict(self) -> dict[str, str | float]:
        """API リクエスト用の JSON オブジェクトへ変換する

        Returns:
            dict[str, str | float]: None のフィールドを除いた単語データ
        """
        values: dict[str, str | float | None] = {
            "written": self.written,
            "spoken": self.spoken,
            "classname": self.classname,
            "alternativewritten": self.alternative_written,
            "biasing": self.biasing,
        }
        return {key: value for key, value in values.items() if value is not None}


class _HttpDictionaryTransport:
    """標準ライブラリで実装した辞書 API トランスポート"""

    def __init__(self, timeout: float) -> None:
        """HTTP 接続タイムアウトを保持する

        Args:
            timeout (float): HTTP 接続のタイムアウト秒数
        """
        self._timeout = timeout

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        """HTTP リクエストを送り、ステータスコードと本文を返す

        Args:
            method (str): HTTP メソッド
            url (str): リクエスト URL
            headers (dict[str, str]): HTTP リクエストヘッダー
            body (bytes | None): HTTP リクエスト本文

        Returns:
            tuple[int, bytes]: HTTP ステータスコードとレスポンス本文

        Raises:
            ConfigurationError: URL が絶対 HTTP(S) URL でない場合
        """
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("base_url must be an absolute HTTP or HTTPS URL")

        connection_class = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        connection = connection_class(parsed.netloc, timeout=self._timeout)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        try:
            connection.request(method, target, body=body, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()


def _response_body_text(body: bytes) -> str:
    """レスポンス本文を表示用の文字列へ変換する"""
    return body.decode("utf-8", errors="replace")


def _raise_invalid_response(message: str, status_code: int, body: bytes) -> NoReturn:
    """不正な辞書 API レスポンスを例外として送出する

    Args:
        message (str): レスポンスが不正な理由
        status_code (int): HTTP ステータスコード
        body (bytes): レスポンス本文

    Raises:
        DictionaryApiError: レスポンスが API の期待形式でない場合
    """
    body_text = _response_body_text(body)
    raise DictionaryApiError(
        f"Dictionary API returned an invalid response: {message}",
        status_code=status_code,
        body=body_text,
        raw_body=body,
    )


def _load_json_response(body: bytes, status_code: int) -> object:
    """JSON レスポンスを Python オブジェクトへ変換する

    Args:
        body (bytes): レスポンス本文
        status_code (int): HTTP ステータスコード

    Returns:
        object: JSON をデコードした値

    Raises:
        DictionaryApiError: JSON のデコードに失敗した場合
    """
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DictionaryApiError(
            f"Dictionary API returned invalid JSON: {exc}",
            status_code=status_code,
            body=_response_body_text(body),
            raw_body=body,
        ) from exc


def _parse_optional_string(
    item: dict[str, object],
    key: str,
    status_code: int,
    body: bytes,
) -> str | None:
    """レスポンス内の任意文字列フィールドを検証する"""
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        _raise_invalid_response(f"profilewords field '{key}' must be a string", status_code, body)
    return value


def _parse_profile_word(item: dict[str, object], status_code: int, body: bytes, index: int) -> ProfileWord:
    """JSON オブジェクトを ProfileWord へ変換する"""
    written = item.get("written")
    if not isinstance(written, str):
        _raise_invalid_response(f"profilewords[{index}].written must be a string", status_code, body)

    biasing_value = item.get("biasing")
    if biasing_value is None:
        biasing = None
    elif isinstance(biasing_value, bool) or not isinstance(biasing_value, (int, float)):
        _raise_invalid_response(f"profilewords[{index}].biasing must be a number", status_code, body)
    else:
        biasing = float(biasing_value)

    try:
        return ProfileWord(
            written=written,
            spoken=_parse_optional_string(item, "spoken", status_code, body),
            classname=_parse_optional_string(item, "classname", status_code, body),
            alternative_written=_parse_optional_string(item, "alternativewritten", status_code, body),
            biasing=biasing,
        )
    except ConfigurationError as exc:
        raise DictionaryApiError(
            f"Dictionary API returned an invalid profile word at index {index}: {exc}",
            status_code=status_code,
            body=_response_body_text(body),
            raw_body=body,
        ) from exc


def _parse_profile_words_response(body: bytes, status_code: int) -> tuple[ProfileWord, ...]:
    """単語一覧レスポンスを ProfileWord のタプルへ変換する"""
    parsed = _load_json_response(body, status_code)
    if not isinstance(parsed, dict):
        _raise_invalid_response("response must be a JSON object", status_code, body)

    profilewords = parsed.get("profilewords")
    if not isinstance(profilewords, list):
        _raise_invalid_response("profilewords must be an array", status_code, body)

    words: list[ProfileWord] = []
    for index, item in enumerate(profilewords):
        if not isinstance(item, dict):
            _raise_invalid_response(f"profilewords[{index}] must be an object", status_code, body)
        words.append(_parse_profile_word(item, status_code, body, index))
    return tuple(words)


def _parse_classnames_response(body: bytes, status_code: int) -> tuple[str, ...]:
    """クラス名一覧レスポンスを文字列のタプルへ変換する"""
    parsed = _load_json_response(body, status_code)
    if not isinstance(parsed, dict):
        _raise_invalid_response("response must be a JSON object", status_code, body)

    classnames = parsed.get("classnames")
    if not isinstance(classnames, list):
        _raise_invalid_response("classnames must be an array", status_code, body)
    for index, classname in enumerate(classnames):
        if not isinstance(classname, str):
            _raise_invalid_response(f"classnames[{index}] must be a string", status_code, body)
    return tuple(classnames)


class UserDictionaryClient:
    """ユーザー辞書登録 API のクライアント

    登録 API は単語の追加ではなく、指定した単語一覧による全件置換を行う

    Args:
        api_key (str | None): API キー、省略時は環境変数 AMIVOICE_API_KEY を使用する
        base_url (str): ユーザー辞書 API のベース URL
        timeout (float): HTTP 接続のタイムアウト秒数
        transport (DictionaryTransport | None): テスト用トランスポート

    Raises:
        AuthenticationError: API キーが引数にも環境変数にもない場合
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = 30.0,
        transport: DictionaryTransport | None = None,
    ) -> None:
        """クライアント設定とトランスポートを初期化する

        Args:
            api_key (str | None): API キー、省略時は環境変数 AMIVOICE_API_KEY を使用する
            base_url (str): ユーザー辞書 API のベース URL
            timeout (float): HTTP 接続のタイムアウト秒数
            transport (DictionaryTransport | None): テスト用トランスポート

        Raises:
            AuthenticationError: API キーが引数にも環境変数にもない場合
        """
        resolved_api_key = api_key if api_key is not None else os.environ.get("AMIVOICE_API_KEY")
        if resolved_api_key is None:
            raise AuthenticationError("AMIVOICE_API_KEY is not set")
        self._api_key = resolved_api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport if transport is not None else _HttpDictionaryTransport(timeout)

    def register_words(
        self,
        engine: str,
        profile_id: str,
        words: Sequence[ProfileWord],
        *,
        sampling_rate: SamplingRate | None = None,
    ) -> tuple[ProfileWord, ...]:
        """プロファイルの単語を全件置換して登録する

        既存の単語へ追加する操作ではないため、追加したい単語を含む全件を指定する

        Args:
            engine (str): 接続エンジン名
            profile_id (str): プロファイル ID
            words (Sequence[ProfileWord]): 置換後の単語一覧
            sampling_rate (Literal["8k", "16k"] | None): 対象サンプリングレート

        Returns:
            tuple[ProfileWord, ...]: API が受け付けた単語一覧

        Raises:
            DictionaryApiError: API がエラーを返した場合、またはレスポンスが不正な場合
        """
        body = _serialize_profile_words(words)
        status_code, response_body = self._request(
            "POST",
            self._profilewords_url(engine, profile_id, sampling_rate),
            body,
        )
        return _parse_profile_words_response(response_body, status_code)

    def get_words(
        self,
        engine: str,
        profile_id: str,
        *,
        sampling_rate: SamplingRate | None = None,
    ) -> tuple[ProfileWord, ...]:
        """プロファイルに登録された単語を取得する

        Args:
            engine (str): 接続エンジン名
            profile_id (str): プロファイル ID
            sampling_rate (Literal["8k", "16k"] | None): 対象サンプリングレート

        Returns:
            tuple[ProfileWord, ...]: 登録済みの単語一覧

        Raises:
            DictionaryApiError: API がエラーを返した場合、またはレスポンスが不正な場合
        """
        status_code, response_body = self._request(
            "GET",
            self._profilewords_url(engine, profile_id, sampling_rate),
            None,
        )
        return _parse_profile_words_response(response_body, status_code)

    def clear_words(
        self,
        engine: str,
        profile_id: str,
        *,
        sampling_rate: SamplingRate | None = None,
    ) -> None:
        """プロファイルの単語を全件削除する

        空の単語一覧を登録することで全件置換を行う

        Args:
            engine (str): 接続エンジン名
            profile_id (str): プロファイル ID
            sampling_rate (Literal["8k", "16k"] | None): 対象サンプリングレート

        Raises:
            DictionaryApiError: API がエラーを返した場合、またはレスポンスが不正な場合
        """
        body = _serialize_profile_words(())
        status_code, response_body = self._request(
            "POST",
            self._profilewords_url(engine, profile_id, sampling_rate),
            body,
        )
        _parse_profile_words_response(response_body, status_code)

    def list_classnames(self, engine: str) -> tuple[str, ...]:
        """接続エンジンで利用できる単語クラス名を取得する

        Args:
            engine (str): 接続エンジン名

        Returns:
            tuple[str, ...]: 利用可能なクラス名一覧

        Raises:
            DictionaryApiError: API がエラーを返した場合、またはレスポンスが不正な場合
        """
        status_code, response_body = self._request("GET", self._classnames_url(engine), None)
        return _parse_classnames_response(response_body, status_code)

    def _request(self, method: str, url: str, body: bytes | None) -> tuple[int, bytes]:
        """認証ヘッダー付きで辞書 API にリクエストする

        Raises:
            ConnectionFailedError: 通信に失敗した場合
            DictionaryApiError: API が 2xx 以外のステータスを返した場合
        """
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        try:
            status_code, response_body = self._transport.request(method, url, headers, body)
        except OSError as exc:
            raise ConnectionFailedError(f"Dictionary API connection failed: {exc}") from exc
        if not 200 <= status_code < 300:
            body_text = _response_body_text(response_body)
            raise DictionaryApiError(
                f"Dictionary API request failed with HTTP {status_code}: {body_text}",
                status_code=status_code,
                body=body_text,
                raw_body=response_body,
            )
        return status_code, response_body

    def _profilewords_url(self, engine: str, profile_id: str, sampling_rate: SamplingRate | None) -> str:
        """プロファイル単語 API の URL を構築する"""
        url = f"{self._base_url}/profilewords/{quote(engine, safe='')}/{quote(profile_id, safe='')}"
        if sampling_rate is not None:
            url = f"{url}?adf={quote(sampling_rate, safe='')}"
        return url

    def _classnames_url(self, engine: str) -> str:
        """クラス名一覧 API の URL を構築する"""
        return f"{self._base_url}/classnames/{quote(engine, safe='')}"


def _serialize_profile_words(words: Sequence[ProfileWord]) -> bytes:
    """ProfileWord の一覧を API リクエスト本文へ変換する"""
    payload = {"profilewords": [word.to_dict() for word in words]}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
