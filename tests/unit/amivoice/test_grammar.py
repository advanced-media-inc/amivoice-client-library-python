"""ルールグラマ指定ヘルパーのユニットテスト"""

import base64
import gzip

import pytest

from amivoice import RULE_GRAMMAR_ENGINE, build_grammar_file_names, encode_grammar
from amivoice.exceptions import ConfigurationError


def test_encode_grammar_fixed_input_returns_deterministic_gzip_base64() -> None:
    """固定したグラマ本文が決定論的な GZIP + Base64 になることを確認する"""
    grammar = "#JSGF V1.0; grammar test;"

    encoded = encode_grammar(grammar)
    repeated_encoded = encode_grammar(grammar)
    decoded = gzip.decompress(base64.b64decode(encoded))

    assert encoded == repeated_encoded
    assert decoded == grammar.encode("utf-8")


def test_encode_grammar_bytes_round_trip_returns_original_grammar() -> None:
    """Bytes で渡したグラマ本文を復号すると元のバイト列に戻ることを確認する"""
    grammar = b"#JSGF V1.0; grammar bytes;"

    encoded = encode_grammar(grammar)
    decoded = gzip.decompress(base64.b64decode(encoded))

    assert decoded == grammar


def test_build_grammar_file_names_single_grammar_returns_engine_and_grammar() -> None:
    """単一グラマの指定文字列にエンジン名と区切り文字が含まれることを確認する"""
    result = build_grammar_file_names("encoded-grammar")

    assert result == f"{RULE_GRAMMAR_ENGINE}|encoded-grammar"


def test_build_grammar_file_names_multiple_grammars_uses_pipe_separator() -> None:
    """複数グラマを通常の区切り文字で連結できることを確認する"""
    result = build_grammar_file_names("grammar-1", "https://example.com/grammar-2")

    assert result == f"{RULE_GRAMMAR_ENGINE}|grammar-1|https://example.com/grammar-2"


def test_build_grammar_file_names_fallback_uses_double_pipe_separator() -> None:
    """フォールバック指定で複数グラマを二重区切り文字で連結できることを確認する"""
    result = build_grammar_file_names("grammar-1", "grammar-2", fallback=True)

    assert result == f"{RULE_GRAMMAR_ENGINE}|grammar-1||grammar-2"


def test_build_grammar_file_names_accepts_custom_engine_and_mixed_grammars() -> None:
    """カスタムエンジンと URL やエンコード済み本文を混在して指定できることを確認する"""
    result = build_grammar_file_names(
        encode_grammar("grammar"),
        "https://example.com/grammar.gram",
        engine="custom-engine",
    )

    assert result == "custom-engine|" + encode_grammar("grammar") + "|https://example.com/grammar.gram"


def test_build_grammar_file_names_without_grammars_invalid_raise_ConfigurationError() -> None:
    """グラマを指定しない場合に ConfigurationError が送出されることを確認する"""
    with pytest.raises(ConfigurationError, match="At least one grammar"):
        build_grammar_file_names()
