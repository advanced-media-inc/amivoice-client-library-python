"""Validate built wheel and source distribution artifacts."""

import argparse
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from packaging.utils import (
    InvalidSdistFilename,
    InvalidWheelFilename,
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import InvalidVersion, Version


class PackageArtifactError(ValueError):
    """Indicate that package artifacts contain an unexpected file or version"""


def _validate_archive_member_path(member_name: str) -> None:
    path = PurePosixPath(member_name)
    if path.is_absolute() or ".." in path.parts:
        raise PackageArtifactError(f"Package artifact contains an unsafe path: {member_name}")


def _validate_wheel_contents(wheel_path: Path, distribution_name: str, expected_version: Version) -> None:
    distribution_prefix = canonicalize_name(distribution_name).replace("-", "_")
    metadata_prefix = f"{distribution_prefix}-{expected_version}.dist-info/"
    required_paths = {"amivoice/py.typed"}

    try:
        with zipfile.ZipFile(wheel_path) as wheel_archive:
            members = wheel_archive.namelist()
    except (OSError, zipfile.BadZipFile) as error:
        raise PackageArtifactError(f"Unable to read wheel artifact: {wheel_path}") from error

    for member_name in members:
        _validate_archive_member_path(member_name)
        if not (member_name.startswith("amivoice/") or member_name.startswith("com/") or member_name.startswith(metadata_prefix)):
            raise PackageArtifactError(f"Wheel contains a file outside the package allowlist: {member_name}")

    if not required_paths.issubset(members):
        raise PackageArtifactError("Wheel does not contain amivoice/py.typed")
    if f"{metadata_prefix}METADATA" not in members or f"{metadata_prefix}RECORD" not in members:
        raise PackageArtifactError("Wheel metadata is incomplete")


def _validate_sdist_contents(sdist_path: Path, distribution_name: str, expected_version: Version) -> None:
    distribution_prefix = canonicalize_name(distribution_name).replace("-", "_")
    archive_prefix = f"{distribution_prefix}-{expected_version}"
    allowed_root_files = {"LICENSE", "PKG-INFO", "README.md", "pyproject.toml", "setup.cfg"}
    allowed_source_prefixes = (
        f"{archive_prefix}/src/amivoice",
        f"{archive_prefix}/src/com",
        f"{archive_prefix}/src/{distribution_prefix}.egg-info",
    )

    try:
        with tarfile.open(sdist_path, mode="r:gz") as sdist_archive:
            members = sdist_archive.getmembers()
    except (OSError, tarfile.TarError) as error:
        raise PackageArtifactError(f"Unable to read source distribution artifact: {sdist_path}") from error

    for member in members:
        _validate_archive_member_path(member.name)
        if member.issym() or member.islnk():
            raise PackageArtifactError(f"Source distribution contains a symbolic link: {member.name}")
        relative_name = member.name.removeprefix(f"{archive_prefix}/")
        if member.name == archive_prefix or relative_name in allowed_root_files:
            continue
        normalized_member_name = member.name.rstrip("/")
        if (
            any(
                normalized_member_name == prefix or normalized_member_name.startswith(f"{prefix}/")
                for prefix in allowed_source_prefixes
            )
            or normalized_member_name == f"{archive_prefix}/src"
        ):
            continue
        raise PackageArtifactError(f"Source distribution contains a file outside the package allowlist: {member.name}")


def _parse_expected_version(raw_version: str) -> Version:
    try:
        expected_version = Version(raw_version)
    except InvalidVersion as error:
        raise PackageArtifactError(f"Expected package version is invalid: {raw_version}") from error
    if str(expected_version) != raw_version:
        raise PackageArtifactError(f"Expected package version must use canonical PEP 440 text: {raw_version}")
    return expected_version


def validate_package_artifacts(dist_dir: Path, distribution_name: str, raw_version: str) -> tuple[Path, Path]:
    """Validate one wheel and one source distribution against an allowlist

    Args:
        dist_dir: Directory containing the built artifacts
        distribution_name: Expected distribution name
        raw_version: Expected canonical PEP 440 version

    Returns:
        The validated wheel and source distribution paths

    Raises:
        PackageArtifactError: If an artifact is missing, mismatched, or unsafe
    """
    if not dist_dir.is_dir():
        raise PackageArtifactError(f"Distribution directory does not exist: {dist_dir}")

    expected_version = _parse_expected_version(raw_version)
    wheel_paths = sorted(dist_dir.glob("*.whl"))
    sdist_paths = sorted(dist_dir.glob("*.tar.gz"))
    all_files = sorted(path for path in dist_dir.iterdir() if path.is_file())
    if len(wheel_paths) != 1 or len(sdist_paths) != 1 or len(all_files) != 2:
        raise PackageArtifactError("Distribution directory must contain exactly one wheel and one source distribution")

    wheel_path = wheel_paths[0]
    sdist_path = sdist_paths[0]
    expected_name = canonicalize_name(distribution_name)

    try:
        wheel_name, wheel_version, _, _ = parse_wheel_filename(wheel_path.name)
    except InvalidWheelFilename as error:
        raise PackageArtifactError(f"Wheel filename is invalid: {wheel_path.name}") from error
    if str(wheel_name) != expected_name or str(wheel_version) != str(expected_version):
        raise PackageArtifactError(f"Wheel filename does not match {distribution_name} {raw_version}: {wheel_path.name}")

    try:
        sdist_name, sdist_version = parse_sdist_filename(sdist_path.name)
    except InvalidSdistFilename as error:
        raise PackageArtifactError(f"Source distribution filename is invalid: {sdist_path.name}") from error
    if str(sdist_name) != expected_name or str(sdist_version) != str(expected_version):
        raise PackageArtifactError(
            f"Source distribution filename does not match {distribution_name} {raw_version}: {sdist_path.name}"
        )

    _validate_wheel_contents(wheel_path, distribution_name, expected_version)
    _validate_sdist_contents(sdist_path, distribution_name, expected_version)
    return wheel_path, sdist_path


def _parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate wheel and source distribution contents")
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"), help="Directory containing distribution artifacts")
    parser.add_argument("--distribution", required=True, help="Expected distribution name")
    parser.add_argument("--version", required=True, help="Expected canonical package version")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run package artifact validation from the command line

    Args:
        arguments: Optional command line arguments for testing

    Returns:
        Zero when both artifacts pass validation and one otherwise
    """
    parsed_arguments = _parse_arguments(arguments)
    try:
        validate_package_artifacts(parsed_arguments.dist_dir, parsed_arguments.distribution, parsed_arguments.version)
    except PackageArtifactError as error:
        print(f"Package artifact validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
