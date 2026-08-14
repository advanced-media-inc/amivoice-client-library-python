"""Validate formal PyPI releases and compare published artifact hashes."""

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from packaging.version import InvalidVersion, Version

from .testpypi_version import UrlOpener, read_project_base_version
from .validate_package_artifacts import PackageArtifactError, validate_package_artifacts

DISTRIBUTION_NAME = "amivoice-api-client"
PYPI_JSON_URL = f"https://pypi.org/pypi/{DISTRIBUTION_NAME}/json"
MINIMUM_FORMAL_RELEASE_VERSION = Version("0.1.0")
FORMAL_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class PyPIReleaseError(RuntimeError):
    """Indicate that a formal PyPI release cannot continue safely"""


@dataclass(frozen=True)
class PyPIFileMetadata:
    """Store a PyPI filename and its SHA-256 digest"""

    filename: str
    sha256: str


@dataclass(frozen=True)
class PyPIIndexMetadata:
    """Store PyPI release files indexed by release version text"""

    releases: dict[str, tuple[PyPIFileMetadata, ...]]


@dataclass(frozen=True)
class ReleaseManifest:
    """Store the expected distribution files and SHA-256 digests"""

    distribution_name: str
    version: str
    files: dict[str, str]


@dataclass(frozen=True)
class PyPIReleaseState:
    """Store whether a formal release still needs to be uploaded"""

    publish_required: bool
    latest_formal_version: Version | None


def validate_formal_release_version(raw_version: str) -> Version:
    """Validate a canonical X.Y.Z formal release version

    Args:
        raw_version: Version text supplied to the PyPI workflow

    Returns:
        The parsed formal release version

    Raises:
        PyPIReleaseError: If the version is not a supported formal version
    """
    if not FORMAL_VERSION_PATTERN.fullmatch(raw_version):
        raise PyPIReleaseError("PyPI version must use the X.Y.Z formal version format")

    try:
        parsed_version = Version(raw_version)
    except InvalidVersion as error:
        raise PyPIReleaseError("PyPI version is not a valid PEP 440 version") from error

    if parsed_version < MINIMUM_FORMAL_RELEASE_VERSION:
        raise PyPIReleaseError("PyPI version must be at least 0.1.0")
    return parsed_version


def validate_project_release_version(pyproject_path: Path, raw_version: str) -> Version:
    """Require workflow input and project.version to be the same formal version

    Args:
        pyproject_path: Path to the project metadata file
        raw_version: Version text supplied to the workflow

    Returns:
        The validated project release version

    Raises:
        PyPIReleaseError: If input and project metadata differ
    """
    requested_version = validate_formal_release_version(raw_version)
    try:
        project_version = read_project_base_version(pyproject_path)
    except ValueError as error:
        raise PyPIReleaseError("Project version is not a valid formal release version") from error
    if project_version != requested_version:
        raise PyPIReleaseError(
            f"Workflow version does not match pyproject.toml project.version: {raw_version} != {project_version}"
        )
    return requested_version


def fetch_pypi_index(
    index_url: str = PYPI_JSON_URL,
    *,
    timeout_seconds: float = 10.0,
    opener: UrlOpener = urlopen,
) -> PyPIIndexMetadata:
    """Fetch and validate release file hashes from the PyPI JSON API

    Args:
        index_url: PyPI-compatible JSON API URL
        timeout_seconds: Network timeout in seconds
        opener: URL opener injected by tests or callers

    Returns:
        Release metadata, or an empty index when the project is absent

    Raises:
        PyPIReleaseError: If the response is unavailable or malformed
    """
    try:
        with opener(index_url, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", None)
            if status_code is None:
                status_code = response.getcode()
            if status_code >= 400:
                raise PyPIReleaseError(f"PyPI index request failed: {index_url} returned HTTP {status_code}")
            response_body = response.read()
    except HTTPError as error:
        if error.code == 404:
            return PyPIIndexMetadata({})
        raise PyPIReleaseError(f"PyPI index request failed: {index_url} returned HTTP {error.code}") from error
    except (OSError, TimeoutError, URLError) as error:
        raise PyPIReleaseError(f"PyPI index request failed: {index_url}") from error

    try:
        payload = json.loads(response_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PyPIReleaseError(f"PyPI index response was not valid JSON: {index_url}") from error

    if not isinstance(payload, dict) or not isinstance(payload.get("releases"), dict):
        raise PyPIReleaseError(f"PyPI index response did not contain a releases object: {index_url}")

    releases: dict[str, tuple[PyPIFileMetadata, ...]] = {}
    for release_name, file_records in payload["releases"].items():
        if not isinstance(release_name, str) or not isinstance(file_records, list):
            raise PyPIReleaseError(f"PyPI index response contains invalid release metadata: {index_url}")
        releases[release_name] = _parse_pypi_file_records(index_url, file_records)
    return PyPIIndexMetadata(releases)


def _parse_pypi_file_records(index_url: str, file_records: list[object]) -> tuple[PyPIFileMetadata, ...]:
    parsed_files: list[PyPIFileMetadata] = []
    seen_filenames: set[str] = set()
    for file_record in file_records:
        if not isinstance(file_record, dict):
            raise PyPIReleaseError(f"PyPI index response contains invalid file metadata: {index_url}")
        filename = file_record.get("filename")
        digests = file_record.get("digests")
        sha256 = digests.get("sha256") if isinstance(digests, dict) else None
        if not isinstance(filename, str) or not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
            raise PyPIReleaseError(f"PyPI index response contains invalid file hashes: {index_url}")
        if filename in seen_filenames:
            raise PyPIReleaseError(f"PyPI index response contains duplicate filenames: {filename}")
        seen_filenames.add(filename)
        parsed_files.append(PyPIFileMetadata(filename, sha256))
    return tuple(parsed_files)


def find_latest_formal_version(index_metadata: PyPIIndexMetadata) -> Version | None:
    """Find the highest canonical formal version visible on PyPI

    Args:
        index_metadata: Release metadata returned by the PyPI JSON API

    Returns:
        The latest formal version, or None when no formal release exists
    """
    formal_versions: list[Version] = []
    for raw_version in index_metadata.releases:
        if not FORMAL_VERSION_PATTERN.fullmatch(raw_version):
            continue
        try:
            parsed_version = Version(raw_version)
        except InvalidVersion:
            continue
        if str(parsed_version) == raw_version and parsed_version >= MINIMUM_FORMAL_RELEASE_VERSION:
            formal_versions.append(parsed_version)
    return max(formal_versions, default=None)


def calculate_file_sha256(file_path: Path) -> str:
    """Calculate the SHA-256 digest of a distribution file

    Args:
        file_path: Path to a file to hash

    Returns:
        Lowercase hexadecimal SHA-256 digest

    Raises:
        PyPIReleaseError: If the file cannot be read
    """
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise PyPIReleaseError(f"Unable to hash release artifact: {file_path}") from error
    return digest.hexdigest()


def write_release_manifest(
    dist_dir: Path,
    manifest_path: Path,
    distribution_name: str,
    raw_version: str,
) -> ReleaseManifest:
    """Validate formal artifacts and write a deterministic SHA-256 manifest

    Args:
        dist_dir: Directory containing the wheel and source distribution
        manifest_path: Destination path for the JSON manifest
        distribution_name: Expected distribution name
        raw_version: Expected formal version

    Returns:
        The manifest written to disk

    Raises:
        PyPIReleaseError: If validation or writing fails
        PackageArtifactError: If distribution contents are invalid
    """
    version = validate_formal_release_version(raw_version)
    wheel_path, sdist_path = validate_package_artifacts(dist_dir, distribution_name, str(version))
    files = {path.name: calculate_file_sha256(path) for path in sorted((wheel_path, sdist_path))}
    manifest = ReleaseManifest(distribution_name, str(version), files)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(_manifest_to_json(manifest), indent=2) + "\n", encoding="utf-8")
    return manifest


def read_release_manifest(manifest_path: Path) -> ReleaseManifest:
    """Read and validate a release SHA-256 manifest

    Args:
        manifest_path: Path to the JSON manifest

    Returns:
        The validated release manifest

    Raises:
        PyPIReleaseError: If the manifest is missing or malformed
    """
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PyPIReleaseError(f"Release manifest could not be read: {manifest_path}") from error
    if not isinstance(payload, dict):
        raise PyPIReleaseError("Release manifest must be a JSON object")
    distribution_name = payload.get("distribution")
    raw_version = payload.get("version")
    file_records = payload.get("files")
    if not isinstance(distribution_name, str) or not isinstance(raw_version, str) or not isinstance(file_records, list):
        raise PyPIReleaseError("Release manifest has an invalid structure")
    version = validate_formal_release_version(raw_version)

    files: dict[str, str] = {}
    for file_record in file_records:
        if not isinstance(file_record, dict):
            raise PyPIReleaseError("Release manifest contains invalid file metadata")
        filename = file_record.get("filename")
        sha256 = file_record.get("sha256")
        if not isinstance(filename, str) or not isinstance(sha256, str) or not SHA256_PATTERN.fullmatch(sha256):
            raise PyPIReleaseError("Release manifest contains an invalid SHA-256 digest")
        if filename in files:
            raise PyPIReleaseError(f"Release manifest contains duplicate filenames: {filename}")
        files[filename] = sha256
    if len(files) != 2:
        raise PyPIReleaseError("Release manifest must contain exactly two distribution files")
    return ReleaseManifest(distribution_name, str(version), files)


def verify_local_release_manifest(dist_dir: Path, manifest: ReleaseManifest) -> None:
    """Verify local artifact names and hashes against a release manifest

    Args:
        dist_dir: Directory containing downloaded or built artifacts
        manifest: Expected release manifest

    Raises:
        PyPIReleaseError: If local artifacts do not match the manifest
    """
    actual_files = sorted(path for path in dist_dir.iterdir() if path.is_file())
    actual_hashes = {path.name: calculate_file_sha256(path) for path in actual_files}
    if actual_hashes != manifest.files:
        raise PyPIReleaseError("Local release artifacts do not match the SHA-256 manifest")


def determine_pypi_release_state(
    index_metadata: PyPIIndexMetadata,
    version: Version,
    manifest: ReleaseManifest,
) -> PyPIReleaseState:
    """Determine whether a formal version may be uploaded or is already identical

    Args:
        index_metadata: Current PyPI release metadata
        version: Validated requested formal version
        manifest: Expected local artifact manifest

    Returns:
        Publication state for the requested version

    Raises:
        PyPIReleaseError: If the version is not newer or existing files differ
    """
    existing_files = index_metadata.releases.get(str(version))
    latest_formal_version = find_latest_formal_version(index_metadata)
    if existing_files is None:
        if latest_formal_version is not None and version <= latest_formal_version:
            raise PyPIReleaseError(f"Requested version {version} is not newer than PyPI {latest_formal_version}")
        return PyPIReleaseState(True, latest_formal_version)

    existing_hashes = {file_metadata.filename: file_metadata.sha256 for file_metadata in existing_files}
    if existing_hashes != manifest.files:
        raise PyPIReleaseError(f"PyPI already contains different artifacts for version {version}")
    return PyPIReleaseState(False, latest_formal_version)


def verify_pypi_release(index_metadata: PyPIIndexMetadata, manifest: ReleaseManifest) -> None:
    """Verify that PyPI contains exactly the artifacts in a release manifest

    Args:
        index_metadata: Current PyPI release metadata
        manifest: Expected release manifest

    Raises:
        PyPIReleaseError: If the requested release is missing or differs
    """
    existing_files = index_metadata.releases.get(manifest.version)
    if existing_files is None:
        raise PyPIReleaseError(f"PyPI does not contain release version {manifest.version}")
    existing_hashes = {file_metadata.filename: file_metadata.sha256 for file_metadata in existing_files}
    if existing_hashes != manifest.files:
        raise PyPIReleaseError(f"PyPI artifacts do not match the release manifest for {manifest.version}")


def _manifest_to_json(manifest: ReleaseManifest) -> dict[str, object]:
    return {
        "distribution": manifest.distribution_name,
        "version": manifest.version,
        "files": [{"filename": filename, "sha256": manifest.files[filename]} for filename in sorted(manifest.files)],
    }


def _parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate and reconcile a formal PyPI release")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-version", help="Validate project and workflow versions")
    validate_parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"))
    validate_parser.add_argument("--version", required=True)

    manifest_parser = subparsers.add_parser("write-manifest", help="Write a release artifact manifest")
    manifest_parser.add_argument("--dist-dir", type=Path, required=True)
    manifest_parser.add_argument("--manifest", type=Path, required=True)
    manifest_parser.add_argument("--distribution", default=DISTRIBUTION_NAME)
    manifest_parser.add_argument("--version", required=True)

    state_parser = subparsers.add_parser("check-pypi", help="Check whether PyPI needs the release upload")
    state_parser.add_argument("--dist-dir", type=Path, required=True)
    state_parser.add_argument("--manifest", type=Path, required=True)
    state_parser.add_argument("--distribution", default=DISTRIBUTION_NAME)
    state_parser.add_argument("--version", required=True)
    state_parser.add_argument("--output", choices=("text", "github-output"), default="text")

    verify_parser = subparsers.add_parser("verify-pypi", help="Verify a published PyPI release")
    verify_parser.add_argument("--dist-dir", type=Path, required=True)
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--distribution", default=DISTRIBUTION_NAME)
    verify_parser.add_argument("--version", required=True)
    verify_parser.add_argument("--output", choices=("text", "github-output"), default="text")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run formal PyPI release validation from the command line

    Args:
        arguments: Optional command line arguments for testing

    Returns:
        Zero when the requested operation succeeds and one otherwise
    """
    parsed_arguments = _parse_arguments(arguments)
    try:
        if parsed_arguments.command == "validate-version":
            version = validate_project_release_version(parsed_arguments.pyproject, parsed_arguments.version)
            print(f"version={version}")
        elif parsed_arguments.command == "write-manifest":
            write_release_manifest(
                parsed_arguments.dist_dir,
                parsed_arguments.manifest,
                parsed_arguments.distribution,
                parsed_arguments.version,
            )
        elif parsed_arguments.command == "check-pypi":
            manifest = read_release_manifest(parsed_arguments.manifest)
            verify_local_release_manifest(parsed_arguments.dist_dir, manifest)
            requested_version = validate_formal_release_version(parsed_arguments.version)
            if manifest.version != str(requested_version) or manifest.distribution_name != parsed_arguments.distribution:
                raise PyPIReleaseError("Release manifest does not match the requested PyPI release")
            state = determine_pypi_release_state(fetch_pypi_index(), requested_version, manifest)
            print(f"publish_required={'true' if state.publish_required else 'false'}")
            if state.latest_formal_version is not None:
                print(f"latest_formal_version={state.latest_formal_version}")
        elif parsed_arguments.command == "verify-pypi":
            manifest = read_release_manifest(parsed_arguments.manifest)
            requested_version = validate_formal_release_version(parsed_arguments.version)
            if manifest.version != str(requested_version) or manifest.distribution_name != parsed_arguments.distribution:
                raise PyPIReleaseError("Release manifest does not match the requested PyPI release")
            verify_local_release_manifest(parsed_arguments.dist_dir, manifest)
            verify_pypi_release(fetch_pypi_index(), manifest)
            print(f"verified_version={manifest.version}")
    except (PackageArtifactError, PyPIReleaseError, ValueError) as error:
        print(f"PyPI release validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
