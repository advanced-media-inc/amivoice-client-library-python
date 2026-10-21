"""配布後の非同期クライアントの公開契約を検証する"""

from pathlib import Path

import pytest

import amivoice
from tools.release import package_smoke_test


@pytest.mark.parametrize(
    "name",
    [
        "AmiVoiceAsyncClient",
        "AsyncJobSnapshot",
        "AsyncJobSubmission",
        "AsyncRecognitionResult",
        "AsyncHttpApiError",
        "AsyncJobError",
        "AsyncJobTimeoutError",
    ],
)
def test_smoke_missing_async_export_invalid_raise_PackageSmokeTestError(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """非同期APIのexport漏れを検出する"""
    # Given: 正常なメタデータと欠けた公開API
    monkeypatch.setattr(package_smoke_test.metadata, "version", lambda name: "1.0.0")
    monkeypatch.setattr(package_smoke_test.metadata, "files", lambda name: [Path("amivoice/py.typed")])
    monkeypatch.delattr(amivoice, name)
    # When / Then: 配布物を正常としない
    with pytest.raises(package_smoke_test.PackageSmokeTestError, match="public"):
        package_smoke_test.run_package_smoke_test("amivoice-api-client", "1.0.0")
