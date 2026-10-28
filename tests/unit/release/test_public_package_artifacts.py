"""旧レイヤーを再配布しないことと公開APIの必須ファイルを検証する"""

import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.unit.release.package_artifact_test_helpers import create_valid_package_artifacts, write_tar_member
from tools.release.validate_package_artifacts import PackageArtifactError, validate_package_artifacts


@pytest.mark.parametrize("name", ["com/__init__.py", "com/amivoice/hrp/Hrp.py", "amivoice/_transport.py"])
def test_validate_package_artifacts_obsolete_wheel_invalid_raise_PackageArtifactError(tmp_path: Path, name: str) -> None:
    """旧パッケージと廃止された通信アダプターの混入を拒否する"""
    # Given: 公開パッケージに旧ファイルが混入したwheel
    create_valid_package_artifacts(tmp_path)
    with zipfile.ZipFile(tmp_path / "amivoice_api_client-1.0.0-py3-none-any.whl", "a") as archive:
        archive.writestr(name, "")
    # When / Then: 許可リスト内に見えるアダプターも拒否する
    expected_error = "obsolete transport adapter" if name == "amivoice/_transport.py" else "outside the package allowlist"
    with pytest.raises(PackageArtifactError, match=expected_error):
        validate_package_artifacts(tmp_path, "amivoice-api-client", "1.0.0")


@pytest.mark.parametrize("name", ["src/com/__init__.py", "src/amivoice/_transport.py"])
def test_validate_package_artifacts_obsolete_sdist_invalid_raise_PackageArtifactError(tmp_path: Path, name: str) -> None:
    """sdistからの再ビルドでも旧レイヤーを復活させない"""
    # Given: 旧ファイルを含むsdist、正しいwheelはそのままにする
    create_valid_package_artifacts(tmp_path)
    path = tmp_path / "amivoice_api_client-1.0.0.tar.gz"
    with tarfile.open(path, "r:gz") as original:
        contents = [(member.name, original.extractfile(member).read()) for member in original.getmembers()]
    with tarfile.open(path, "w:gz") as archive:
        for member_name, body in contents:
            write_tar_member(archive, member_name, body)
        write_tar_member(archive, "amivoice_api_client-1.0.0/" + name)
    # When / Then: 旧ファイルを許可しない
    expected_error = "obsolete transport adapter" if name == "src/amivoice/_transport.py" else "outside the package allowlist"
    with pytest.raises(PackageArtifactError, match=expected_error):
        validate_package_artifacts(tmp_path, "amivoice-api-client", "1.0.0")


@pytest.mark.parametrize(
    "missing",
    [
        "amivoice/__init__.py",
        "amivoice/client.py",
        "amivoice/async_client.py",
        "amivoice/async_models.py",
        "amivoice/sentiment_analysis.py",
        "amivoice/py.typed",
    ],
)
def test_validate_package_artifacts_missing_public_module_invalid_raise_PackageArtifactError(
    tmp_path: Path, missing: str
) -> None:
    """公開APIに必要なファイルが欠けたwheelを拒否する"""
    # Given: 正常な配布物から1ファイルだけ取り除く
    create_valid_package_artifacts(tmp_path)
    path = tmp_path / "amivoice_api_client-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(path) as original:
        contents = [(name, original.read(name)) for name in original.namelist() if name != missing]
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in contents:
            archive.writestr(name, body)
    # When / Then: 不完全な公開パッケージを配布しない
    with pytest.raises(PackageArtifactError, match="Wheel is missing required public API files"):
        validate_package_artifacts(tmp_path, "amivoice-api-client", "1.0.0")
