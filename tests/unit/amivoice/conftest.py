"""公開APIの回帰テストで使う匿名化済み応答を提供する"""

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def recorded_responses() -> dict[str, object]:
    """認証情報と発話IDを削除した固定応答を読み込む"""
    path = Path(__file__).resolve().parents[2] / "fixtures/amivoice/recorded_responses.json"
    return json.loads(path.read_text(encoding="utf-8"))
