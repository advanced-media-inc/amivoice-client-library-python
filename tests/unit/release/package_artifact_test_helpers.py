"""Helpers for creating valid package artifacts in release tests."""

import io
import tarfile
import zipfile
from pathlib import Path


def write_tar_member(archive: tarfile.TarFile, name: str, content: bytes = b"") -> None:
    """Add a regular file to a test source distribution"""
    member = tarfile.TarInfo(name)
    member.size = len(content)
    archive.addfile(member, io.BytesIO(content))


def create_valid_package_artifacts(dist_dir: Path) -> None:
    """Create minimal valid wheel and source distribution archives"""
    wheel_path = dist_dir / "amivoice_api_client-1.0.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, mode="w") as wheel_archive:
        for member_name in (
            "amivoice/py.typed",
            "com/__init__.py",
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
            f"{archive_prefix}/src/com/__init__.py",
            f"{archive_prefix}/src/amivoice_api_client.egg-info/PKG-INFO",
        ):
            write_tar_member(sdist_archive, member_name)
