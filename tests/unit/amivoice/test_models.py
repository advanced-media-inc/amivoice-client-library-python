# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

"""models モジュールのユニットテスト。"""

import json
from dataclasses import FrozenInstanceError

import pytest

from amivoice.exceptions import RecognitionError
from amivoice.models import (
    NotificationEvent,
    RecognitionResult,
    Token,
    UtteranceEvent,
    UtteranceResult,
)
from amivoice.models import (
    parse_result as _parse_result,
)


def test_RecognitionResult_frozen_field_invalid_raise_FrozenInstanceError() -> None:
    """RecognitionResult がイミュータブルで、フィールドへの代入が禁止されることを確認する。"""
    # Given: RecognitionResult インスタンス
    result = RecognitionResult(raw='{"text": "hello"}', data={"text": "hello"})

    # When / Then: フィールドに代入すると FrozenInstanceError が送出される
    with pytest.raises(FrozenInstanceError):
        result.raw = '{"text": "updated"}'  # type: ignore[misc]


def test_RecognitionResult_defaults_valid_return_is_error_false() -> None:
    """RecognitionResult のデフォルト値を確認する。"""
    # Given: 最小限の引数で生成した RecognitionResult
    # When: RecognitionResult を生成する
    result = RecognitionResult(raw='{"text": "hello"}', data={"text": "hello"})

    # Then: is_error が False、session_id が None
    assert result.is_error is False
    assert result.session_id is None
    assert result.results == ()


def test_parse_result_full_utterance_valid_return_typed_result() -> None:
    """フル仕様の発話結果を型付きモデルへ変換できることを確認する。"""
    # Given: 発話区間、単語、信頼度、時刻、話者、言語を含む認識結果
    raw = json.dumps(
        {
            "results": [
                {
                    "text": "こんにちは世界",
                    "tokens": [
                        {
                            "written": "こんにちは",
                            "spoken": "コンニチハ",
                            "confidence": 1,
                            "starttime": 100,
                            "endtime": 500,
                            "label": "speaker0",
                            "language": "ja",
                        }
                    ],
                    "confidence": 0.98,
                    "starttime": 100,
                    "endtime": 1000,
                    "tags": ["greeting"],
                    "rulename": "general",
                }
            ],
            "utteranceid": "utterance-1",
            "text": "こんにちは世界",
            "code": "",
        }
    )

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: 発話区間と単語の各フィールドが型付きで返る
    assert result.utterance_id == "utterance-1"
    assert result.results == (
        UtteranceResult(
            text="こんにちは世界",
            tokens=(
                Token(
                    written="こんにちは",
                    spoken="コンニチハ",
                    confidence=1.0,
                    starttime=100,
                    endtime=500,
                    label="speaker0",
                    language="ja",
                ),
            ),
            confidence=0.98,
            starttime=100,
            endtime=1000,
            tags=("greeting",),
            rulename="general",
        ),
    )


def test_parse_result_e2e_token_without_spoken_valid_return_none() -> None:
    """Spoken がない E2E エンジンの結果をパースできることを確認する。"""
    # Given: spoken を含まない単語結果
    raw = json.dumps({"results": [{"text": "hello", "tokens": [{"written": "hello"}]}]})

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: spoken と省略可能なフィールドが None になる
    token = result.results[0].tokens[0]
    assert token.written == "hello"
    assert token.spoken is None
    assert token.confidence is None
    assert token.starttime is None
    assert token.endtime is None
    assert token.label is None
    assert token.language is None


def test_parse_result_speaker_label_valid_return_label() -> None:
    """話者ダイアライゼーションのラベルをパースできることを確認する。"""
    # Given: 話者ラベルを含む単語結果
    raw = '{"results":[{"text":"hello","tokens":[{"written":"hello","label":"speaker1"}]}]}'

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: 話者ラベルが単語モデルに設定される
    assert result.results[0].tokens[0].label == "speaker1"


def test_parse_result_multilingual_token_valid_return_language() -> None:
    """多言語認識の言語ラベルをパースできることを確認する。"""
    # Given: 言語ラベルを含む単語結果
    raw = '{"results":[{"text":"hello","tokens":[{"written":"hello","language":"en"}]}]}'

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: 言語ラベルが単語モデルに設定される
    assert result.results[0].tokens[0].language == "en"


def test_parse_result_punctuation_token_without_timing_valid_return_none() -> None:
    """時刻と信頼度がない句読点トークンをパースできることを確認する。"""
    # Given: written と spoken のみを持つトークン結果
    raw = '{"results":[{"text":"、","tokens":[{"written":"、","spoken":"、"}]}]}'

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: 時刻と信頼度が None になる
    token = result.results[0].tokens[0]
    assert token.written == "、"
    assert token.spoken == "、"
    assert token.starttime is None
    assert token.endtime is None
    assert token.confidence is None


def test_parse_result_without_results_key_valid_return_empty_results() -> None:
    """Results キーがない結果では空のタプルを返すことを確認する。"""
    # Given: results キーがない認識結果
    raw = '{"text":"hello","code":""}'

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: results が空のタプルになる
    assert result.results == ()


def test_parse_result_partial_result_valid_return_typed_result() -> None:
    """途中結果相当のテキストと written のみの結果をパースできることを確認する。"""
    # Given: text と tokens[].written のみを含む結果
    raw = '{"text":"hello","results":[{"text":"hello","tokens":[{"written":"hello"}]}]}'

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: 必須フィールドだけの発話結果が返る
    assert result.results == (UtteranceResult(text="hello", tokens=(Token(written="hello"),)),)


@pytest.mark.parametrize(
    "raw",
    [
        '{"results":{}}',
        '{"results":["invalid"]}',
        '{"results":[{"text":"hello","tokens":["invalid"]}]}',
    ],
)
def test_parse_result_invalid_structure_invalid_raise_RecognitionError(raw: str) -> None:
    """認識結果の配列や要素が不正な場合に RecognitionError が送出されることを確認する。"""
    # Given: results または tokens の構造が不正な JSON
    # When / Then: parse_result を呼び出すと RecognitionError が送出される
    with pytest.raises(RecognitionError):
        _parse_result(raw)


@pytest.mark.parametrize("field", ["confidence", "starttime", "endtime"])
def test_parse_result_bool_numeric_field_invalid_raise_RecognitionError(field: str) -> None:
    """数値フィールドに bool を指定した場合に RecognitionError が送出されることを確認する。"""
    # Given: 発話結果の数値フィールドに bool を指定した JSON
    raw_data = {"results": [{"text": "hello", "tokens": [{"written": "hello"}], field: True}]}
    raw = json.dumps(raw_data)

    # When / Then: parse_result を呼び出すと RecognitionError が送出される
    with pytest.raises(RecognitionError):
        _parse_result(raw)


def test_RecognitionResult_utterance_id_without_key_valid_return_none() -> None:
    """Utteranceid キーがない場合に utterance_id が None を返すことを確認する。"""
    # Given: utteranceid キーを持たない RecognitionResult
    result = RecognitionResult(raw='{"text":"hello"}', data={"text": "hello"})

    # When / Then: utterance_id プロパティを参照する
    assert result.utterance_id is None


def test_Token_frozen_field_invalid_raise_FrozenInstanceError() -> None:
    """Token がイミュータブルで、フィールドへの代入が禁止されることを確認する。"""
    # Given: Token インスタンス
    token = Token(written="hello")

    # When / Then: フィールドに代入すると FrozenInstanceError が送出される
    with pytest.raises(FrozenInstanceError):
        token.written = "updated"  # type: ignore[misc]


def test_UtteranceResult_frozen_field_invalid_raise_FrozenInstanceError() -> None:
    """UtteranceResult がイミュータブルで、フィールドへの代入が禁止されることを確認する。"""
    # Given: UtteranceResult インスタンス
    utterance = UtteranceResult(text="hello")

    # When / Then: フィールドに代入すると FrozenInstanceError が送出される
    with pytest.raises(FrozenInstanceError):
        utterance.text = "updated"  # type: ignore[misc]


def test_RecognitionResult_text_with_text_key_valid_return_text() -> None:
    """Data に "text" キーがある場合に text プロパティがその値を返すことを確認する。"""
    # Given: data に "text" キーを持つ RecognitionResult
    result = RecognitionResult(raw='{"text": "こんにちは"}', data={"text": "こんにちは"})

    # When / Then: text プロパティが "text" の値を返す
    assert result.text == "こんにちは"


def test_RecognitionResult_text_without_text_key_valid_return_empty_string() -> None:
    """Data に "text" キーがない場合に text プロパティが空文字列を返すことを確認する。"""
    # Given: data に "text" キーを持たない RecognitionResult
    result = RecognitionResult(raw='{"code": "E001"}', data={"code": "E001"}, is_error=True)

    # When / Then: text プロパティが空文字列を返す
    assert result.text == ""


def test_RecognitionResult_text_frozen_invalid_raise_FrozenInstanceError() -> None:
    """Text プロパティへの代入が FrozenInstanceError を送出することを確認する。"""
    # Given: RecognitionResult インスタンス
    result = RecognitionResult(raw='{"text": "hello"}', data={"text": "hello"})

    # When / Then: text プロパティに代入すると FrozenInstanceError が送出される
    with pytest.raises((FrozenInstanceError, AttributeError)):
        result.text = "overwrite"  # type: ignore[misc]


def test_parse_result_normal_json_valid_return_result() -> None:
    """正常な JSON を渡すと RecognitionResult が返ることを確認する。"""
    # Given: 正常な JSON 文字列
    raw = '{"text": "hello", "confidence": 0.9}'

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: 正常な RecognitionResult が返る
    assert result.raw == '{"text": "hello", "confidence": 0.9}'
    assert result.data == {"text": "hello", "confidence": 0.9}
    assert result.is_error is False


def test_parse_result_r_command_prefix_invalid_raise_RecognitionError() -> None:
    """R コマンドプレフィックス付き応答を渡すと RecognitionError が送出されることを確認する。"""
    # Given: R コマンドプレフィックス付きのエラー JSON
    raw = '\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}'

    # When / Then: parse_result を呼び出すと RecognitionError が送出され、result にエラー情報が格納される
    with pytest.raises(RecognitionError) as exc_info:
        _parse_result(raw)

    assert exc_info.value.result is not None
    assert exc_info.value.result.is_error is True
    assert exc_info.value.result.raw == '{"code": "E001", "message": "bad request"}'
    assert exc_info.value.result.data == {"code": "E001", "message": "bad request"}


def test_parse_result_error_with_message_field_invalid_raise_RecognitionError() -> None:
    """エラー JSON に message フィールドがある場合にそのメッセージで RecognitionError が送出されることを確認する。"""
    # Given: message フィールド付きのエラー JSON
    raw = '\x01\x01\x01\x01\x01{"code": "E001", "message": "bad request"}'

    # When / Then: parse_result を呼び出すと message フィールドのメッセージで RecognitionError が送出される
    with pytest.raises(RecognitionError, match="bad request"):
        _parse_result(raw)


def test_parse_result_error_code_without_message_invalid_raise_RecognitionError() -> None:
    """エラー JSON に message フィールドがない場合に code フィールドで RecognitionError が送出されることを確認する。"""
    # Given: message フィールドなしのエラー JSON
    raw = '\x01\x01\x01\x01\x01{"code": "E001"}'

    # When / Then: parse_result を呼び出すと code フィールドのメッセージで RecognitionError が送出される
    with pytest.raises(RecognitionError, match="E001"):
        _parse_result(raw)


def test_parse_result_raise_on_error_false_invalid_return_error_result() -> None:
    """raise_on_error=False の場合にエラー結果がそのまま返ることを確認する。"""
    # Given: R コマンドプレフィックス付きのエラー JSON
    raw = '\x01\x01\x01\x01\x01{"error": "bad request"}'

    # When: raise_on_error=False で parse_result を呼び出す
    result = _parse_result(raw, raise_on_error=False)

    # Then: 例外は送出されず is_error=True の結果が返る
    assert result.raw == '{"error": "bad request"}'
    assert result.data == {"error": "bad request"}
    assert result.is_error is True


def test_parse_result_invalid_json_invalid_raise_RecognitionError() -> None:
    """不正な JSON を渡すと RecognitionError が送出されることを確認する。"""
    # Given: 不正な JSON 文字列
    raw = "not-json"

    # When / Then: parse_result を呼び出すと RecognitionError が送出される
    with pytest.raises(RecognitionError):
        _parse_result(raw)


@pytest.mark.parametrize(
    "code",
    ["-", "+", "!", ">", "<", "#", "$", "%", "b", "x", "c", "?", "^"],
)
def test_parse_result_non_o_error_code_invalid_return_is_error_true(code: str) -> None:
    """エラーコード（空文字・"o" 以外）が含まれる JSON で is_error が True になることを確認する。"""
    # Given: 各エラーコードを含む JSON（パラメトライズ）
    raw = f'{{"results":[],"text":"","code":"{code}","message":"error"}}'

    # When: raise_on_error=False で parse_result を呼び出す
    result = _parse_result(raw, raise_on_error=False)

    # Then: is_error が True
    assert result.is_error is True


def test_parse_result_http_error_code_default_invalid_raise_RecognitionError() -> None:
    """HTTP エラーコード "-" が含まれる JSON でデフォルト動作が RecognitionError を送出することを確認する。"""
    # Given: HTTP エラーコード "-" を含む JSON
    raw = '{"results":[],"text":"","code":"-","message":"received illegal service authorization"}'

    # When / Then: parse_result を呼び出すと RecognitionError が送出される
    with pytest.raises(RecognitionError, match="received illegal service authorization"):
        _parse_result(raw)


def test_parse_result_empty_code_valid_return_is_error_false() -> None:
    """Code フィールドが空文字の場合に is_error が False になることを確認する。"""
    # Given: code が空文字の JSON
    raw = '{"text":"hello","code":"","message":""}'

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: is_error が False
    assert result.is_error is False


def test_parse_result_o_code_valid_return_is_error_false() -> None:
    """Code フィールドが "o" の場合に is_error が False になることを確認する。"""
    # Given: code が "o" の JSON（閾値以下で棄却された認識結果）
    raw = (
        '{"results":[],"text":"","code":"o","message":"recognition result is rejected because confidence is below the threshold"}'
    )

    # When: parse_result を呼び出す
    result = _parse_result(raw)

    # Then: is_error が False
    assert result.is_error is False


def test_UtteranceEvent_frozen_field_invalid_raise_FrozenInstanceError() -> None:
    """UtteranceEvent がイミュータブルで、フィールドへの代入が禁止されることを確認する。"""
    # Given: UtteranceEvent インスタンス
    event = UtteranceEvent(type="started", time=1000)

    # When: フィールドへのアクセスが正常であることを確認する
    assert event.type == "started"
    assert event.time == 1000

    # Then: フィールドに代入すると FrozenInstanceError が送出される
    with pytest.raises(FrozenInstanceError):
        event.time = 2000  # type: ignore[misc]


def test_NotificationEvent_frozen_field_invalid_raise_FrozenInstanceError() -> None:
    """NotificationEvent がイミュータブルで、フィールドへの代入が禁止されることを確認する。"""
    # Given: NotificationEvent インスタンス
    event = NotificationEvent(event_id="E001", event_message="ready")

    # When: フィールドへのアクセスが正常であることを確認する
    assert event.event_id == "E001"
    assert event.event_message == "ready"

    # Then: フィールドに代入すると FrozenInstanceError が送出される
    with pytest.raises(FrozenInstanceError):
        event.event_message = "updated"  # type: ignore[misc]
