"""公開APIだけで動作する配布物のスモークテスト"""

from pathlib import Path

import pytest

import amivoice
from tools.release import package_smoke_test


@pytest.fixture
def installed_package_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    """インストール済みパッケージのメタデータだけを差し替える"""
    monkeypatch.setattr(package_smoke_test.metadata, "version", lambda name: "1.0.0")
    monkeypatch.setattr(
        package_smoke_test.metadata, "files", lambda name: [Path("amivoice/__init__.py"), Path("amivoice/py.typed")]
    )


def test_run_package_smoke_test_public_api_valid_return_without_network(installed_package_metadata: None) -> None:
    """環境の実キーとネットワークを使わず公開クライアントを生成する"""
    # Given: テスト用のメタデータとネットワークガード
    # When / Then: comをimportせず新規公開APIも確認できる
    assert package_smoke_test.main(["--version", "1.0.0"]) == 0


@pytest.mark.parametrize("name", ["com/__init__.py", "com/amivoice/wrp/Wrp.py", "amivoice/_transport.py"])
def test_run_package_smoke_test_obsolete_file_invalid_raise_PackageSmokeTestError(
    installed_package_metadata: None, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    """そのdistributionが所有する旧ファイルを検出する"""
    # Given: 旧レイヤーのファイルが含まれるメタデータ
    monkeypatch.setattr(package_smoke_test.metadata, "files", lambda distribution: [Path(name)])
    # When / Then: 関係ない他distributionのcomではなく自身のファイルを検査する
    with pytest.raises(package_smoke_test.PackageSmokeTestError, match="obsolete"):
        package_smoke_test.run_package_smoke_test("amivoice-api-client", "1.0.0")


def test_run_package_smoke_test_missing_export_invalid_raise_PackageSmokeTestError(
    installed_package_metadata: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """追加した感情パラメータAPIのエクスポート漏れを検出する"""
    # Given: 公開APIの一部が欠けたパッケージ
    monkeypatch.delattr(amivoice, "SentimentAnalysisClient")
    # When / Then: 成功扱いしない
    with pytest.raises(package_smoke_test.PackageSmokeTestError, match="public"):
        package_smoke_test.run_package_smoke_test("amivoice-api-client", "1.0.0")


def test_run_package_smoke_test_missing_typing_marker_invalid_raise_PackageSmokeTestError(
    installed_package_metadata: None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """型マーカーがないインストールを拒否する"""
    # Given: 型マーカーのないパッケージディレクトリ
    monkeypatch.setattr(amivoice, "__path__", [str(tmp_path)])
    # When / Then: 配布漏れとして通知する
    with pytest.raises(package_smoke_test.PackageSmokeTestError, match=r"py\.typed"):
        package_smoke_test.run_package_smoke_test("amivoice-api-client", "1.0.0")


def test_run_package_smoke_test_version_mismatch_invalid_return_error(installed_package_metadata: None) -> None:
    """バージョン不一致をCLIの失敗終了で示す"""
    # Given: 1.0.0のインストールメタデータ
    # When / Then: 別バージョンの要求を拒否する
    assert package_smoke_test.main(["--version", "2.0.0"]) == 1
