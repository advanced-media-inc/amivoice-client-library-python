"""Resolve the next TestPyPI development version from package indexes."""

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from packaging.version import InvalidVersion, Version

DISTRIBUTION_NAME = "amivoice-api-client"
TESTPYPI_JSON_URL = f"https://test.pypi.org/pypi/{DISTRIBUTION_NAME}/json"
PYPI_JSON_URL = f"https://pypi.org/pypi/{DISTRIBUTION_NAME}/json"
MINIMUM_RELEASE_VERSION = Version("0.1.0")
BASE_VERSION_PATTERN = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class ReleaseVersionError(ValueError):
    """Indicate that a package release version cannot be used"""


class ReleaseIndexError(RuntimeError):
    """Indicate that a package index could not be read safely"""


class UrlResponse(Protocol):
    """Describe the response methods used by the release index reader"""

    def __enter__(self) -> "UrlResponse":
        """Return the opened response"""

    def __exit__(self, exception_type: object, exception_value: object, traceback: object) -> None:
        """Close the opened response"""

    def getcode(self) -> int:
        """Return the HTTP status code"""

    def read(self) -> bytes:
        """Read the response body"""


UrlOpener = Callable[..., UrlResponse]
ReleaseMetadataFetcher = Callable[[str], "ReleaseIndexMetadata"]


@dataclass(frozen=True)
class ReleaseIndexMetadata:
    """Store release names returned by a package index JSON API"""

    release_names: tuple[str, ...]


@dataclass(frozen=True)
class TestPyPIReleaseResolution:
    """Store the validated base and next TestPyPI development versions"""

    base_version: Version
    development_version: Version


def validate_base_version(raw_version: str) -> Version:
    """Validate a public X.Y.Z base version that is at least 0.1.0

    Args:
        raw_version: Version text read from project metadata

    Returns:
        The parsed public version

    Raises:
        ReleaseVersionError: If the version is not an allowed public version
    """
    if not BASE_VERSION_PATTERN.fullmatch(raw_version):
        raise ReleaseVersionError("Base version must use the X.Y.Z public version format")

    try:
        parsed_version = Version(raw_version)
    except InvalidVersion as error:
        raise ReleaseVersionError("Base version is not a valid PEP 440 version") from error

    if parsed_version < MINIMUM_RELEASE_VERSION:
        raise ReleaseVersionError("Base version must be at least 0.1.0")

    return parsed_version


def read_project_base_version(pyproject_path: Path) -> Version:
    """Read and validate project.version from a pyproject.toml file

    Args:
        pyproject_path: Path to the project metadata file

    Returns:
        The validated public base version

    Raises:
        ReleaseVersionError: If project metadata is missing or invalid
    """
    try:
        with pyproject_path.open("rb") as pyproject_file:
            project_metadata = tomllib.load(pyproject_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ReleaseVersionError(f"Unable to read project metadata: {pyproject_path}") from error

    project = project_metadata.get("project")
    if not isinstance(project, dict):
        raise ReleaseVersionError("Project metadata does not contain a [project] table")

    raw_version = project.get("version")
    if not isinstance(raw_version, str):
        raise ReleaseVersionError("Project metadata does not contain project.version")

    return validate_base_version(raw_version)


def fetch_release_metadata(
    index_url: str,
    *,
    timeout_seconds: float = 10.0,
    opener: UrlOpener = urlopen,
) -> ReleaseIndexMetadata:
    """Fetch release names from a PyPI-compatible JSON API

    Args:
        index_url: JSON API URL to request
        timeout_seconds: Network timeout in seconds
        opener: URL opener injected by tests or callers

    Returns:
        Release names from the index, or an empty set for HTTP 404

    Raises:
        ReleaseIndexError: If the index cannot be read without ambiguity
    """
    try:
        with opener(index_url, timeout=timeout_seconds) as response:
            status_code = getattr(response, "status", None)
            if status_code is None:
                status_code = response.getcode()
            if status_code >= 400:
                raise ReleaseIndexError(f"Release index request failed: {index_url} returned HTTP {status_code}")
            response_body = response.read()
    except HTTPError as error:
        if error.code == 404:
            return ReleaseIndexMetadata(())
        raise ReleaseIndexError(f"Release index request failed: {index_url} returned HTTP {error.code}") from error
    except (OSError, TimeoutError, URLError) as error:
        raise ReleaseIndexError(f"Release index request failed: {index_url}") from error

    try:
        payload = json.loads(response_body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReleaseIndexError(f"Release index response was not valid JSON: {index_url}") from error

    if not isinstance(payload, dict):
        raise ReleaseIndexError(f"Release index response was not an object: {index_url}")

    releases = payload.get("releases")
    if not isinstance(releases, dict) or not all(isinstance(name, str) for name in releases):
        raise ReleaseIndexError(f"Release index response did not contain a valid releases object: {index_url}")

    return ReleaseIndexMetadata(tuple(releases))


def calculate_next_development_version(base_version: Version, release_names: Iterable[str]) -> Version:
    """Calculate the next exact base-version.devN release number

    Args:
        base_version: Validated public base version
        release_names: Release names currently visible on TestPyPI

    Returns:
        The next development version, starting at dev1
    """
    development_numbers: list[int] = []

    for release_name in release_names:
        try:
            parsed_release = Version(release_name)
        except InvalidVersion:
            continue

        if (
            not parsed_release.is_devrelease
            or parsed_release.dev is None
            or parsed_release.dev < 1
            or parsed_release.post is not None
            or parsed_release.local is not None
        ):
            continue

        expected_release = Version(f"{base_version}.dev{parsed_release.dev}")
        if parsed_release == expected_release:
            development_numbers.append(parsed_release.dev)

    next_number = max(development_numbers, default=0) + 1
    return Version(f"{base_version}.dev{next_number}")


def contains_equivalent_release(base_version: Version, release_names: Iterable[str]) -> bool:
    """Check whether release names contain a PEP 440-equivalent version

    Args:
        base_version: Version to find in the release names
        release_names: Release names returned by a package index

    Returns:
        True when an equivalent release version is present
    """
    for release_name in release_names:
        try:
            if Version(release_name) == base_version:
                return True
        except InvalidVersion:
            continue

    return False


def resolve_testpypi_release(
    pyproject_path: Path,
    *,
    distribution_name: str = DISTRIBUTION_NAME,
    metadata_fetcher: ReleaseMetadataFetcher = fetch_release_metadata,
) -> TestPyPIReleaseResolution:
    """Resolve a TestPyPI version while preventing a published base release collision

    Args:
        pyproject_path: Path to the project metadata file
        distribution_name: Distribution name used to construct index URLs
        metadata_fetcher: JSON metadata fetcher injected by tests or callers

    Returns:
        The validated base version and next TestPyPI development version

    Raises:
        ReleaseVersionError: If the base version is already formally released
        ReleaseIndexError: If either package index cannot be read safely
    """
    base_version = read_project_base_version(pyproject_path)
    testpypi_url = f"https://test.pypi.org/pypi/{distribution_name}/json"
    pypi_url = f"https://pypi.org/pypi/{distribution_name}/json"
    testpypi_metadata = metadata_fetcher(testpypi_url)
    pypi_metadata = metadata_fetcher(pypi_url)

    if contains_equivalent_release(base_version, testpypi_metadata.release_names) or contains_equivalent_release(
        base_version, pypi_metadata.release_names
    ):
        raise ReleaseVersionError(f"Base version {base_version} is already published")

    development_version = calculate_next_development_version(base_version, testpypi_metadata.release_names)
    return TestPyPIReleaseResolution(base_version, development_version)


def _parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resolve the next TestPyPI development version")
    parser.add_argument("--pyproject", type=Path, default=Path("pyproject.toml"), help="Path to pyproject.toml")
    parser.add_argument(
        "--distribution",
        default=DISTRIBUTION_NAME,
        help="Distribution name used for the package index JSON APIs",
    )
    parser.add_argument(
        "--output",
        choices=("version", "github-output"),
        default="version",
        help="Output format for the resolved version",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run the TestPyPI version resolver command line interface

    Args:
        arguments: Optional command line arguments for testing

    Returns:
        Zero on success and one when resolution fails
    """
    parsed_arguments = _parse_arguments(arguments)
    try:
        resolution = resolve_testpypi_release(parsed_arguments.pyproject, distribution_name=parsed_arguments.distribution)
    except (ReleaseIndexError, ReleaseVersionError) as error:
        print(f"TestPyPI version resolution failed: {error}", file=sys.stderr)
        return 1

    if parsed_arguments.output == "github-output":
        print(f"base_version={resolution.base_version}")
        print(f"version={resolution.development_version}")
    else:
        print(resolution.development_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
