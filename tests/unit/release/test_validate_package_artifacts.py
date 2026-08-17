"""Tests for built package artifact validation."""

import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.unit.release.package_artifact_test_helpers import create_valid_package_artifacts, write_tar_member
from tools.release.validate_package_artifacts import PackageArtifactError, validate_package_artifacts


def test_validate_package_artifacts_valid_returns_artifact_paths(tmp_path: Path) -> None:
    """A wheel and source distribution with allowed contents pass validation"""
    # Given: one valid wheel and source distribution
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    create_valid_package_artifacts(dist_dir)

    # When: package artifacts are validated
    artifact_paths = validate_package_artifacts(dist_dir, "amivoice-api-client", "1.0.0")

    # Then: both artifact paths are returned
    assert {path.suffix for path in artifact_paths} == {".whl", ".gz"}


def test_validate_package_artifacts_unexpected_wheel_file_invalid_raise_PackageArtifactError(tmp_path: Path) -> None:
    """A wheel file outside the package allowlist is rejected"""
    # Given: valid artifacts with an unexpected wheel file
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    create_valid_package_artifacts(dist_dir)
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
    create_valid_package_artifacts(dist_dir)
    sdist_path = dist_dir / "amivoice_api_client-1.0.0.tar.gz"
    archive_prefix = "amivoice_api_client-1.0.0"
    with tarfile.open(sdist_path, mode="w:gz") as sdist_archive:
        for member_name in (
            f"{archive_prefix}/LICENSE",
            f"{archive_prefix}/PKG-INFO",
            f"{archive_prefix}/README.md",
            f"{archive_prefix}/pyproject.toml",
            f"{archive_prefix}/src/amivoice/py.typed",
            f"{archive_prefix}/src/com/__init__.py",
            f"{archive_prefix}/src/amivoice_api_client.egg-info/PKG-INFO",
            f"{archive_prefix}/docs/internal.md",
        ):
            write_tar_member(sdist_archive, member_name)

    # When: package artifacts are validated
    with pytest.raises(PackageArtifactError):
        validate_package_artifacts(dist_dir, "amivoice-api-client", "1.0.0")

    # Then: the unsafe package is not accepted
