# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false

"""ユーザー辞書登録 API クライアントのユニットテスト"""

import json
from dataclasses import dataclass, field
from http.client import IncompleteRead

import pytest

from amivoice import ConnectionFailedError, DictionaryApiError, ProfileWord, UserDictionaryClient
from amivoice.dictionary import build_profile_words
from amivoice.exceptions import AuthenticationError, ConfigurationError


@dataclass
class FakeDictionaryTransport:
    """テスト用の辞書 API トランスポート"""

    responses: list[tuple[int, bytes]] = field(default_factory=list)
    error: Exception | None = None
    requests: list[tuple[str, str, dict[str, str], bytes | None]] = field(default_factory=list)

    def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, bytes]:
        """リクエストを記録し、キューからレスポンスを返す"""
        self.requests.append((method, url, headers, body))
        if self.error is not None:
            raise self.error
        return self.responses.pop(0)


def test_register_words_hybrid_valid_send_request_and_return_words() -> None:
    """ハイブリッド形式の単語を登録し、登録結果を返すことを確認する"""
    # Given: ハイブリッド形式の単語と登録結果を返すフェイクトランスポート
    transport = FakeDictionaryTransport(
        responses=[
            (
                200,
                b'{"profilewords":[{"written":"AmiVoice","spoken":"\\u3042\\u307f\\u307c\\u3044\\u3059","classname":"\\u56fa\\u6709\\u540d\\u8a5e"}]}',
            )
        ]
    )
    client = UserDictionaryClient(api_key="test-key", base_url="https://example.test", transport=transport)
    words = (ProfileWord(written="AmiVoice", spoken="あみぼいす", classname="固有名詞"),)

    # When: ユーザー辞書単語を登録する
    registered = client.register_words("-a/general", "profile id", words, sampling_rate="8k")

    # Then: URL、認証情報、ボディ、戻り値が正しい
    assert registered == words
    assert transport.requests == [
        (
            "POST",
            "https://example.test/profilewords/-a%2Fgeneral/profile%20id?adf=8k",
            {"Authorization": "Bearer test-key", "Content-Type": "application/json"},
            json.dumps(
                {"profilewords": [{"written": "AmiVoice", "spoken": "あみぼいす", "classname": "固有名詞"}]},
                ensure_ascii=False,
            ).encode("utf-8"),
        )
    ]


def test_register_words_e2e_valid_serialize_alternative_and_biasing() -> None:
    """E2E 形式の代替表記と単語強調度をシリアライズすることを確認する"""
    # Given: E2E 形式の単語と空の登録結果
    transport = FakeDictionaryTransport(responses=[(200, b'{"profilewords":[]}')])
    client = UserDictionaryClient(api_key="test-key", transport=transport)
    word = ProfileWord(written="AmiVoice", alternative_written="あみぼいす", biasing=0.75)

    # When: ユーザー辞書単語を登録する
    client.register_words("-e2e", "profile", (word,))

    # Then: E2E 固有の JSON フィールドが送信される
    assert transport.requests[0][3] == json.dumps(
        {"profilewords": [{"written": "AmiVoice", "alternativewritten": "あみぼいす", "biasing": 0.75}]},
        ensure_ascii=False,
    ).encode("utf-8")


@pytest.mark.parametrize("biasing", [-0.1, 1.1])
def test_profile_word_biasing_out_of_range_invalid_raise_ConfigurationError(biasing: float) -> None:
    """単語強調度が範囲外の場合に ConfigurationError が送出されることを確認する"""
    # Given: 0.0 から 1.0 の範囲外の単語強調度
    # When / Then: ProfileWord の生成で ConfigurationError が送出される
    with pytest.raises(ConfigurationError, match="biasing"):
        ProfileWord(written="word", biasing=biasing)


def test_register_words_sampling_rate_omitted_valid_omit_adf_query() -> None:
    """サンプリングレートを省略した場合に adf クエリを付けないことを確認する"""
    # Given: 成功レスポンスを返すフェイクトランスポート
    transport = FakeDictionaryTransport(responses=[(200, b'{"profilewords":[]}')])
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When: サンプリングレートを指定せずに登録する
    client.register_words("-a-general", "profile", ())

    # Then: URL に adf クエリが含まれない
    assert transport.requests[0][1] == "https://acp-api.amivoice.com/profilewords/-a-general/profile"


def test_get_words_unicode_escaped_valid_return_decoded_profile_words() -> None:
    """Unicode エスケープされた取得結果を ProfileWord へ変換することを確認する"""
    # Given: Unicode エスケープを含む取得レスポンス
    transport = FakeDictionaryTransport(
        responses=[(200, b'{"profilewords":[{"written":"\\u65e5\\u672c","spoken":"\\u306b\\u307b\\u3093"}]}')]
    )
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When: 登録済み単語を取得する
    words = client.get_words("-a-general", "profile", sampling_rate="16k")

    # Then: Unicode がデコードされた ProfileWord が返る
    assert words == (ProfileWord(written="日本", spoken="にほん"),)
    assert transport.requests[0][:2] == (
        "GET",
        "https://acp-api.amivoice.com/profilewords/-a-general/profile?adf=16k",
    )
    assert transport.requests[0][2] == {"Authorization": "Bearer test-key"}
    assert transport.requests[0][3] is None


def test_get_words_e2e_actual_response_valid_return_profile_words_without_error() -> None:
    """実APIのE2E応答形式をDictionaryApiErrorなしでProfileWordへ変換することを確認する"""
    # Given: E2Eエンジンが代替表記をspoken、単語強調度をclassnameとして返す応答
    transport = FakeDictionaryTransport(
        responses=[
            (
                200,
                '{"profilewords":[{"written":"AOI","classname":"0.6"},'
                '{"written":"AmiVoice","spoken":"アミボイス","classname":"0.7"}]}'.encode("utf-8"),
            )
        ]
    )
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When: 登録済み単語を取得する
    words = client.get_words("-a2-ja-general", "profile")

    # Then: 混在チェックに接触せず応答どおりのProfileWordが返る
    assert words == (
        ProfileWord(written="AOI", classname="0.6"),
        ProfileWord(written="AmiVoice", spoken="アミボイス", classname="0.7"),
    )


def test_clear_words_valid_send_empty_profile_words() -> None:
    """単語を全削除する場合に空配列を登録することを確認する"""
    # Given: 空の登録結果を返すフェイクトランスポート
    transport = FakeDictionaryTransport(responses=[(200, b'{"profilewords":[]}')])
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When: ユーザー辞書を全削除する
    result = client.clear_words("-a-general", "profile")

    # Then: 戻り値がなく、空の profilewords 配列が送信される
    assert result is None
    assert transport.requests[0][0] == "POST"
    assert json.loads(transport.requests[0][3].decode("utf-8")) == {"profilewords": []}  # type: ignore[union-attr]


def test_list_classnames_valid_return_classname_tuple() -> None:
    """クラス名一覧をタプルへ変換して返すことを確認する"""
    # Given: クラス名一覧を返すフェイクトランスポート
    transport = FakeDictionaryTransport(responses=[(200, '{"classnames":["固有名詞","名前"]}'.encode("utf-8"))])
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When: クラス名一覧を取得する
    classnames = client.list_classnames("-a/general")

    # Then: クラス名のタプルが返る
    assert classnames == ("固有名詞", "名前")
    assert transport.requests[0][:2] == (
        "GET",
        "https://acp-api.amivoice.com/classnames/-a%2Fgeneral",
    )


def test_dictionary_api_non_2xx_invalid_raise_DictionaryApiError_with_status_and_body() -> None:
    """非 2xx レスポンスでステータスと本文を保持した例外が送出されることを確認する"""
    # Given: HTTP 400 とエラー本文を返すフェイクトランスポート
    transport = FakeDictionaryTransport(responses=[(400, b"bad request")])
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When / Then: API 呼び出しで DictionaryApiError が送出される
    with pytest.raises(DictionaryApiError) as exc_info:
        client.get_words("-a-general", "profile")

    assert exc_info.value.status_code == 400
    assert exc_info.value.body == "bad request"


def test_dictionary_api_invalid_json_invalid_raise_DictionaryApiError() -> None:
    """不正な JSON レスポンスで DictionaryApiError が送出されることを確認する"""
    # Given: 不正な JSON を返すフェイクトランスポート
    transport = FakeDictionaryTransport(responses=[(200, b"not-json")])
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When / Then: API 呼び出しで DictionaryApiError が送出される
    with pytest.raises(DictionaryApiError, match="JSON"):
        client.get_words("-a-general", "profile")


def test_dictionary_api_network_failure_invalid_raise_ConnectionFailedError() -> None:
    """通信失敗時に ConnectionFailedError が送出されることを確認する"""
    # Given: OSError を送出するフェイクトランスポート
    transport = FakeDictionaryTransport(error=OSError("connection refused"))
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When / Then: API 呼び出しで ConnectionFailedError が送出される
    with pytest.raises(ConnectionFailedError, match="connection refused") as exc_info:
        client.get_words("-a-general", "profile")

    assert isinstance(exc_info.value.__cause__, OSError)


def test_dictionary_api_http_protocol_failure_invalid_raise_ConnectionFailedError() -> None:
    """HTTP プロトコル障害時に ConnectionFailedError が送出されることを確認する"""
    # Given: 切断された Content-Length 応答を表す HTTP プロトコル例外
    transport = FakeDictionaryTransport(error=IncompleteRead(b"partial", 10))
    client = UserDictionaryClient(api_key="test-key", transport=transport)

    # When / Then: API 呼び出しで ConnectionFailedError が送出される
    with pytest.raises(ConnectionFailedError, match="Dictionary API connection failed") as exc_info:
        client.get_words("-a-general", "profile")

    assert isinstance(exc_info.value.__cause__, IncompleteRead)


def test_user_dictionary_client_http_base_url_invalid_raise_ConfigurationError() -> None:
    """HTTP のベース URL を指定した場合に ConfigurationError が送出されることを確認する"""
    # Given: 平文通信を使用するベース URL
    # When / Then: カスタムトランスポートを使用してもクライアント生成が拒否される
    with pytest.raises(ConfigurationError, match="HTTPS"):
        UserDictionaryClient(
            api_key="test-key",
            base_url="http://example.test",
            transport=FakeDictionaryTransport(),
        )


def test_user_dictionary_client_api_key_missing_invalid_raise_AuthenticationError(monkeypatch: pytest.MonkeyPatch) -> None:
    """API キーと環境変数がない場合に AuthenticationError が送出されることを確認する"""
    # Given: API キーの環境変数を削除する
    monkeypatch.delenv("AMIVOICE_API_KEY", raising=False)

    # When / Then: API キーなしでクライアントを生成すると AuthenticationError が送出される
    with pytest.raises(AuthenticationError):
        UserDictionaryClient()


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        (ProfileWord(written="AmiVoice", spoken="あみぼいす", classname="固有名詞"), "AmiVoice あみぼいす 固有名詞"),
        (ProfileWord(written="WWW", spoken="とりぷるだぶる"), "WWW とりぷるだぶる"),
        (ProfileWord(written="AmiVoice", alternative_written="あみぼいす", biasing=0.75), "AmiVoice あみぼいす 0.75"),
        (ProfileWord(written="AmiVoice"), "AmiVoice"),
    ],
)
def test_build_profile_words_valid_serializes_word_forms(word: ProfileWord, expected: str) -> None:
    """ハイブリッド形式とE2E形式のProfileWordをシリアライズすることを確認する"""
    # Given: ワイヤー形式に変換可能なProfileWord
    # When: profileWords文字列を構築する
    serialized = build_profile_words((word,))

    # Then: 期待する単語形式の文字列が返る
    assert serialized == expected


def test_build_profile_words_e2e_without_alternative_valid_keeps_empty_field() -> None:
    """E2E形式で代替表記を省略した場合に連続スペースを保持することを確認する"""
    # Given: 代替表記を省略して単語強調度だけ指定したProfileWord
    word = ProfileWord(written="AmiVoice", biasing=0.75)

    # When: profileWords文字列を構築する
    serialized = build_profile_words((word,))

    # Then: 代替表記の空フィールドが連続スペースとして保持される
    assert serialized == "AmiVoice  0.75"


@pytest.mark.parametrize(
    ("biasing", "expected"),
    [
        (0.00001, "AmiVoice  0.00001"),
        (1.5e-10, "AmiVoice  0.00000000015"),
        (0.0001, "AmiVoice  0.0001"),
        (1, "AmiVoice  1.0"),
        (0.0, "AmiVoice  0.0"),
    ],
)
def test_build_profile_words_biasing_valid_serialize_decimal_notation(biasing: float, expected: str) -> None:
    """単語強調度を指数表記ではなく小数表記で出力することを確認する"""
    # Given: str(float)では指数表記になる値を含む単語強調度
    word = ProfileWord(written="AmiVoice", biasing=biasing)

    # When: profileWords文字列を構築する
    serialized = build_profile_words((word,))

    # Then: 公式ドキュメントに記載のない指数表記を使わず小数表記で出力される
    assert serialized == expected


def test_build_profile_words_multiple_valid_joins_with_pipe() -> None:
    """複数のProfileWordをパイプ区切りで連結することを確認する"""
    # Given: 2件のProfileWord
    words = (
        ProfileWord(written="AmiVoice", spoken="あみぼいす"),
        ProfileWord(written="WWW", spoken="とりぷるだぶる"),
    )

    # When: profileWords文字列を構築する
    serialized = build_profile_words(words)

    # Then: 単語がパイプ区切りで連結される
    assert serialized == "AmiVoice あみぼいす|WWW とりぷるだぶる"


@pytest.mark.parametrize(
    "fields",
    [
        {"spoken": "あみぼいす", "alternative_written": "あみボイス"},
        {"spoken": "あみぼいす", "biasing": 0.75},
        {"classname": "固有名詞", "alternative_written": "あみボイス"},
        {"classname": "固有名詞", "biasing": 0.75},
    ],
)
def test_profile_word_mixed_fields_invalid_raise_ConfigurationError(fields: dict[str, str | float]) -> None:
    """ハイブリッド形式とE2E形式のフィールド混在でConfigurationErrorが送出されることを確認する"""
    # Given: ハイブリッドとE2Eのフィールドを混在させた値
    # When / Then: ProfileWordの生成でConfigurationErrorが送出される
    with pytest.raises(ConfigurationError, match="mixed"):
        ProfileWord(written="AmiVoice", **fields)  # type: ignore[arg-type]


def test_build_profile_words_classname_without_spoken_invalid_raise_ConfigurationError() -> None:
    """spokenなしでclassnameを指定した場合にConfigurationErrorが送出されることを確認する"""
    # Given: 辞書APIのE2E応答と同じくspokenなしでclassnameを持つProfileWord
    word = ProfileWord(written="AOI", classname="0.6")

    # When / Then: profileWords文字列の構築でConfigurationErrorが送出される
    with pytest.raises(ConfigurationError, match="spoken must be specified"):
        build_profile_words((word,))


@pytest.mark.parametrize("field_name", ["written", "spoken", "classname", "alternative_written"])
def test_build_profile_words_forbidden_character_invalid_raise_ConfigurationError(field_name: str) -> None:
    """単語フィールドに空白またはパイプが含まれる場合にConfigurationErrorが送出されることを確認する"""
    # Given: ワイヤー形式の区切り文字を含むフィールド値
    word_value = "bad value" if field_name.endswith("written") else "bad|value"
    is_e2e = field_name == "alternative_written"
    word = ProfileWord(
        written=word_value if field_name == "written" else "valid",
        spoken=None if is_e2e else word_value if field_name == "spoken" else "valid",
        classname=word_value if field_name == "classname" else None,
        alternative_written=word_value if is_e2e else None,
    )

    # When / Then: profileWords文字列の構築でConfigurationErrorが送出される
    with pytest.raises(ConfigurationError, match="spaces or"):
        build_profile_words((word,))
