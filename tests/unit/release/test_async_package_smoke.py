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
        "SentimentAnalysisResult",
        "SentimentSegment",
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


def test_smoke_diarization_settings_valid_return_constructed_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """スモークテストが新しい公開設定を使用して通信せず初期化する"""
    # Given: 正常なメタデータと本物のクライアントを利用する記録関数
    monkeypatch.setattr(package_smoke_test.metadata, "version", lambda name: "1.0.0")
    monkeypatch.setattr(package_smoke_test.metadata, "files", lambda name: [Path("amivoice/py.typed")])
    original = amivoice.AmiVoiceAsyncClient
    configured = []

    def create_client(*, settings: amivoice.RecognitionSettings, api_key: str) -> amivoice.AmiVoiceAsyncClient:
        configured.append(settings)
        return original(settings=settings, api_key=api_key)

    monkeypatch.setattr(amivoice, "AmiVoiceAsyncClient", create_client)
    # When: スモークテストを実行する
    package_smoke_test.run_package_smoke_test("amivoice-api-client", "1.0.0")
    # Then: インストール後も新フィールドが動作する
    assert len(configured) == 1
    assert configured[0].sentiment_analysis is True
    assert configured[0].speaker_diarization is True
    assert configured[0].diarization_min_speaker == configured[0].diarization_max_speaker == 1
