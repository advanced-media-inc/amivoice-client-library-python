"""READMEと利用ガイドのPython例を実APIなしで実行する"""

import doctest
import json
import re
from pathlib import Path
from textwrap import indent
from urllib.parse import unquote, urlsplit

import pytest

from amivoice._async_audio import MultipartUpload
from amivoice._async_http_transport import AsyncHttpConnection
from amivoice._http_api import HttpApiConnection
from amivoice._params import RecognitionParams

from .amivoice.test_amivoice_client import HttpFake, WebSocketFake

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCUMENTATION_EXAMPLES = [
    pytest.param(code, id=f"{path.stem}-{index}")
    for path in (REPOSITORY_ROOT / "README.md", *sorted((REPOSITORY_ROOT / "docs").glob("usage*.md")))
    for index, code in enumerate(re.findall(r"```python\n(.*?)\n```", path.read_text(encoding="utf-8"), re.DOTALL), start=1)
]


class _IgnoreDocumentationOutput(doctest.OutputChecker):
    """実行時エラーだけを検証し、認識内容や表示順は固定しない"""

    def __init__(self) -> None:
        """ドキュメント例の分岐確認に使う実行結果を保持する"""
        self.outputs: list[str] = []

    def check_output(self, want: str, got: str, optionflags: int) -> bool:
        """内容の一致は別の公開APIテストへ委ね、表示結果だけ記録する"""
        self.outputs.append(got)
        return True


@pytest.mark.parametrize("code", DOCUMENTATION_EXAMPLES)
def test_documentation_python_example_public_api_valid_return_without_network(
    code: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """未定義変数や削除した引数を含む例を、実装の公開APIで検出する"""
    # Given: ファイル、ダミーENV、公開APIが使う通信のフェイク
    monkeypatch.setenv("AMIVOICE_API_KEY", "documentation-dummy")
    monkeypatch.setenv("AMIVOICE_ISSUER_API_KEY", "documentation-issuer-dummy")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "audio.wav").write_bytes(b"audio")
    (tmp_path / "stereo.wav").write_bytes(b"stereo")
    (tmp_path / "Number.gram").write_text("#JSGF V1.0 UTF-8; grammar Number; public <number> = 一;", encoding="utf-8")
    recognition = {"text": "recognized", "code": "", "message": ""}
    monkeypatch.setattr("amivoice.client.HttpRecognitionConnection", lambda: HttpFake(recognition))
    monkeypatch.setattr("amivoice._stream.WebSocketConnection", lambda: WebSocketFake(["A " + json.dumps(recognition)]))
    dictionaries = {}

    def api_response(
        connection: HttpApiConnection, method: str, url: str, headers: dict[str, str], body: bytes | None
    ) -> tuple[int, bytes]:
        path = urlsplit(url).path
        if path.endswith("/issue_service_authorization"):
            return 200, b"documentation-issued-dummy"
        if path.endswith("/result-parameters.json"):
            result = {
                "sentiment_analysis": {
                    "result_parameters": {
                        "definitions": [{"name": "energy", "display_name": "エネルギー", "minimum": 0, "maximum": 100}]
                    }
                }
            }
        elif path.startswith("/classnames/"):
            result = {"classnames": ["固有名詞"]}
        elif path.startswith("/profilewords/") and path.endswith("/"):
            result = {"profileids": ["user01"]}
        elif path.startswith("/profilewords/"):
            if method == "POST":
                dictionaries[url] = json.loads(body)
            result = dictionaries.get(url, {"profilewords": []})
        else:
            raise AssertionError("Documentation requested an unexpected API path")
        return 200, json.dumps(result).encode("utf-8")

    def async_response(  # noqa: PLR0913
        connection: AsyncHttpConnection,
        method: str,
        url: str,
        headers: dict[str, str],
        body: MultipartUpload | None,
        params: RecognitionParams,
        *,
        deadline: float | None = None,
    ) -> tuple[int, bytes]:
        if method == "POST":
            # 分割音声を最後まで消費し、例のファイル所有権も検証する
            assert body is not None
            for _ in body.chunks():
                pass
            return 200, b'{"sessionid":"job1","text":"..."}'
        session_id = unquote(urlsplit(url).path.rsplit("/", 1)[1])
        data = {
            "session_id": session_id,
            "status": "completed",
            **recognition,
            "segments": [
                {
                    "text": "recognized",
                    "results": [
                        {
                            "text": "recognized",
                            "tokens": [
                                {"written": "recognized", "label": "speaker0", "starttime": 0, "endtime": 100},
                                {"written": "unlabeled"},
                            ],
                        }
                    ],
                }
            ],
        }
        return 200, json.dumps(data).encode("utf-8")

    monkeypatch.setattr(HttpApiConnection, "request", api_response)
    monkeypatch.setattr(AsyncHttpConnection, "request", async_response)
    # When: Python例を個別の名前空間で最後まで実行する
    checker = _IgnoreDocumentationOutput()
    runner = doctest.DocTestRunner(checker=checker)
    example = doctest.DocTest(
        [doctest.Example("if True:\n" + indent(code, "    "), "")],
        {"__name__": "documentation_example"},
        "documentation",
        "example.md",
        0,
        None,
    )
    result = runner.run(example, clear_globs=False)
    # Then: 全通信がフェイクで完了し、元のAPIキーは使われない
    assert result.failed == 0
    if 'speaker = token.label if token.label is not None else "ラベルなし"' in code:
        # ラベルあり/なしと時刻あり/なしの両分岐を最後まで実行したことも確認する
        assert example.globs["speaker"] == "ラベルなし"
        assert example.globs["timing"] == "時刻なし"
        output = "".join(checker.outputs)
        assert "[speaker0] recognized (0ms - 100ms)" in output
        assert "[ラベルなし] unlabeled (時刻なし)" in output
