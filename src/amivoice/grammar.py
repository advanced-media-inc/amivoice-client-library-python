"""ルールグラマを AmiVoice API の指定形式へ変換するヘルパー"""

import base64
import gzip

from .constants import Engine
from .exceptions import ConfigurationError


def encode_grammar(grammar: str | bytes) -> str:
    """グラマ本文を GZIP 圧縮して Base64 文字列へ変換する

    Args:
        grammar: UTF-8 でエンコードするグラマ本文またはバイト列

    Returns:
        GZIP 圧縮後の Base64 エンコード文字列
    """
    data = grammar.encode("utf-8") if isinstance(grammar, str) else grammar
    return base64.b64encode(gzip.compress(data, mtime=0)).decode("ascii")


def build_grammar_file_names(
    *grammars: str,
    engine: str = Engine.A_RULE_INPUT_PRIVATE,
    fallback: bool = False,
) -> str:
    """GrammarFileNames に渡すルールグラマ指定文字列を構築する

    各グラマは URL または :func:`encode_grammar` の戻り値をそのまま指定する
    ``fallback`` が True の場合はグラマ間を ``||`` で連結し、前のグラマで
    認識に失敗したときに次のグラマを試すフォールバック指定にする

    Args:
        *grammars: URL または GZIP + Base64 済みのグラマ本文
        engine: 接続エンジン名
        fallback: グラマ間をフォールバック区切りで連結するか

    Returns:
        接続エンジン名とグラマ指定を連結した ``grammarFileNames`` 文字列

    Raises:
        ConfigurationError: グラマが 1 件も指定されていない場合
    """
    if not grammars:
        raise ConfigurationError("At least one grammar must be specified")

    separator = "||" if fallback else "|"
    return f"{engine}|{separator.join(grammars)}"
