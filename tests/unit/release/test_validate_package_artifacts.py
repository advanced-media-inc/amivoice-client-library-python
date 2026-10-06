"""Tests for built package artifact validation."""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from tools.release.validate_package_artifacts import PackageArtifactError, validate_package_artifacts


def write_tar_member(archive: tarfile.TarFile, name: str, content: bytes = b"") -> None:
    """Add a regular file to a test source distribution"""
    member = tarfile.TarInfo(name)
    member.size = len(content)
    archive.addfile(member, io.BytesIO(content))


def create_valid_artifacts(dist_dir: Path) -> None:
    """Create minimal valid wheel and source distribution archives"""
    wheel_path = dist_dir / "amivoice_api_client-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, mode="w") as wheel_archive:
        for member_name in (
            "amivoice/py.typed",
            "amivoice/__init__.py",
            "amivoice/client.py",
            "amivoice/sentiment_analysis.py",
            "amivoice_api_client-1.0.0.dist-info/METADATA",
            "amivoice_api_client-1.0.0.dist-info/RECORD",
        ):
            wheel_archive.writestr(member_name, "")

    sdist_path = dist_dir / "amivoice_api_client-1.0.0.tar.gz"
    archive_prefix = "amivoice_api_client-1.0.0"
    with tarfile.open(sdist_path, mode="w:gz") as sdist_archive:
        for member_name in (
            f"{archive_prefix}/LICENSE",
            f"{archive_prefix}/PKG-INFO",
            f"{archive_prefix}/README.md",
            f"{archive_prefix}/pyproject.toml",
            f"{archive_prefix}/src/amivoice/py.typed",
            f"{archive_prefix}/src/amivoice/__init__.py",
            f"{archive_prefix}/src/amivoice/client.py",
            f"{archive_prefix}/src/amivoice/sentiment_analysis.py",
            f"{archive_prefix}/src/amivoice_api_client.egg-info/PKG-INFO",
        ):
            write_tar_member(sdist_archive, member_name)


def test_validate_package_artifacts_valid_returns_artifact_paths(tmp_path: Path) -> None:
    """A wheel and source distribution with allowed contents pass validation"""
    # Given: one valid wheel and source distribution
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    create_valid_artifacts(dist_dir)

    # When: package artifacts are validated
    artifact_paths = validate_package_artifacts(dist_dir, "amivoice-api-client", "1.0.0")

    # Then: both artifact paths are returned
    assert {path.suffix for path in artifact_paths} == {".whl", ".gz"}


def test_validate_package_artifacts_unexpected_wheel_file_invalid_raise_PackageArtifactError(tmp_path: Path) -> None:
    """A wheel file outside the package allowlist is rejected"""
    # Given: valid artifacts with an unexpected wheel file
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    create_valid_artifacts(dist_dir)
    wheel_path = dist_dir / "amivoice_api_client-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, mode="a") as wheel_archive:
        wheel_archive.writestr("tests/test_unpublished.py", "")

    # When: package artifacts are validated
    with pytest.raises(PackageArtifactError):
        validate_package_artifacts(dist_dir, "amivoice-api-client", "1.0.0")

    # Then: the unsafe package is not accepted


def test_validate_package_artifacts_unexpected_sdist_file_invalid_raise_PackageArtifactError(tmp_path: Path) -> None:
    """A source distribution file outside the package allowlist is rejected"""
    # Given: valid artifacts with an unexpected source distribution file
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    create_valid_artifacts(dist_dir)
    sdist_path = dist_dir / "amivoice_api_client-1.0.0.tar.gz"
    archive_prefix = "amivoice_api_client-1.0.0"
    with tarfile.open(sdist_path, mode="w:gz") as sdist_archive:
        for member_name in (
            f"{archive_prefix}/LICENSE",
            f"{archive_prefix}/PKG-INFO",
            f"{archive_prefix}/README.md",
            f"{archive_prefix}/pyproject.toml",
            f"{archive_prefix}/src/amivoice/py.typed",
            f"{archive_prefix}/src/amivoice/__init__.py",
            f"{archive_prefix}/src/amivoice/client.py",
            f"{archive_prefix}/src/amivoice/sentiment_analysis.py",
            f"{archive_prefix}/src/amivoice_api_client.egg-info/PKG-INFO",
            f"{archive_prefix}/docs/internal.md",
        ):
            write_tar_member(sdist_archive, member_name)

    # When: package artifacts are validated
    with pytest.raises(PackageArtifactError):
        validate_package_artifacts(dist_dir, "amivoice-api-client", "1.0.0")

    # Then: the unsafe package is not accepted
