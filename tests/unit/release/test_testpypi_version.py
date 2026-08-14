"""Tests for TestPyPI development version resolution."""

import json
from pathlib import Path
from urllib.error import HTTPError

import pytest
from packaging.version import Version

from tools.release.testpypi_version import (
    ReleaseIndexError,
    ReleaseIndexMetadata,
    ReleaseVersionError,
    calculate_next_development_version,
    fetch_release_metadata,
    read_project_base_version,
    resolve_testpypi_release,
    validate_base_version,
)


class FakeUrlResponse:
    """Provide the response interface needed by the release index reader"""

    def __init__(self, payload: object, status_code: int = 200) -> None:
        """Create a response with a JSON body and HTTP status"""
        self._body = json.dumps(payload).encode()
        self.status = status_code

    def __enter__(self) -> "FakeUrlResponse":
        """Return this fake response as a context manager"""
        return self

    def __exit__(self, exception_type: object, exception_value: object, traceback: object) -> None:
        """Close this fake response context"""
        return None

    def getcode(self) -> int:
        """Return the configured HTTP status"""
        return self.status

    def read(self) -> bytes:
        """Return the encoded JSON response body"""
        return self._body


def write_pyproject_version(tmp_path: Path, version: str) -> Path:
    """Create a minimal pyproject.toml for version resolver tests"""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(f'[project]\nname = "example"\nversion = "{version}"\n', encoding="utf-8")
    return pyproject_path


def test_validate_base_version_public_valid_return_version() -> None:
    """A public base version is returned as a parsed PEP 440 version"""
    # Given: a supported public version
    raw_version = "0.1.0"

    # When: the base version is validated
    validated_version = validate_base_version(raw_version)

    # Then: the parsed version is returned
    assert validated_version == Version("0.1.0")


@pytest.mark.parametrize(
    "raw_version",
    ["0.0.1", "1.0.0.dev1", "1.0.0rc1", "1.0.0.post1", "1.0.0+local", "01.0.0", "1.0"],
)
def test_validate_base_version_non_public_invalid_raise_ReleaseVersionError(raw_version: str) -> None:
    """A non-public or pre-0.1.0 version is rejected"""
    # Given: a version that is not an allowed public base version

    # When: the base version is validated
    with pytest.raises(ReleaseVersionError):
        validate_base_version(raw_version)

    # Then: validation raises ReleaseVersionError


def test_calculate_next_development_version_maximum_valid_return_next() -> None:
    """The next number follows the maximum exact dev release"""
    # Given: TestPyPI releases with valid, unrelated, and excluded versions
    base_version = Version("1.0.0")
    release_names = (
        "1.0.0.dev1",
        "1.0.0.dev2",
        "1.0.0.dev10",
        "1.0.0.dev10+local",
        "1.0.0.post1",
        "1.0.0rc1",
        "1.1.0.dev99",
        "1.1.13b1",
    )

    # When: the next TestPyPI development version is calculated
    next_version = calculate_next_development_version(base_version, release_names)

    # Then: only the maximum exact dev release is considered
    assert next_version == Version("1.0.0.dev11")


def test_calculate_next_development_version_no_visible_release_valid_return_dev1() -> None:
    """A missing or pruned release history starts at dev1"""
    # Given: no matching TestPyPI release remains visible
    base_version = Version("1.0.0")

    # When: the next TestPyPI development version is calculated
    next_version = calculate_next_development_version(base_version, ("1.1.13b1", "1.0.0rc1"))

    # Then: the first development number is selected
    assert next_version == Version("1.0.0.dev1")


def test_fetch_release_metadata_not_found_valid_return_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """An HTTP 404 means that the package project has no releases"""

    # Given: a package index opener returning HTTP 404
    def open_not_found(url: str, *, timeout: float) -> FakeUrlResponse:
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    # When: release metadata is fetched
    metadata = fetch_release_metadata("https://test.pypi.org/example/json", opener=open_not_found)

    # Then: no visible release is returned
    assert metadata == ReleaseIndexMetadata(())


def test_fetch_release_metadata_server_error_invalid_raise_ReleaseIndexError() -> None:
    """A server error fails closed instead of selecting a possibly reused version"""

    # Given: a package index returning HTTP 503
    def open_server_error(url: str, *, timeout: float) -> FakeUrlResponse:
        return FakeUrlResponse({}, status_code=503)

    # When: release metadata is fetched
    with pytest.raises(ReleaseIndexError):
        fetch_release_metadata("https://test.pypi.org/example/json", opener=open_server_error)

    # Then: version resolution is not allowed to continue


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), ValueError("invalid JSON")])
def test_fetch_release_metadata_unavailable_invalid_raise_ReleaseIndexError(failure: Exception) -> None:
    """A timeout or malformed JSON fails closed"""

    # Given: an index opener that returns an unsafe response
    def open_unavailable(url: str, *, timeout: float) -> FakeUrlResponse:
        if isinstance(failure, TimeoutError):
            raise failure
        response = FakeUrlResponse({})
        response._body = b"not-json"
        return response

    # When: release metadata is fetched
    with pytest.raises(ReleaseIndexError):
        fetch_release_metadata("https://test.pypi.org/example/json", opener=open_unavailable)

    # Then: no version is selected from incomplete index data


def test_resolve_testpypi_release_base_published_invalid_raise_ReleaseVersionError(tmp_path: Path) -> None:
    """A formally published base version prevents development uploads"""
    # Given: project metadata and a base release visible on PyPI
    pyproject_path = write_pyproject_version(tmp_path, "1.0.0")
    metadata_by_url = {
        "https://test.pypi.org/pypi/amivoice-api-client/json": ReleaseIndexMetadata(()),
        "https://pypi.org/pypi/amivoice-api-client/json": ReleaseIndexMetadata(("1.0.0",)),
    }

    def fetch_metadata(url: str) -> ReleaseIndexMetadata:
        return metadata_by_url[url]

    # When: the TestPyPI release is resolved
    with pytest.raises(ReleaseVersionError):
        resolve_testpypi_release(pyproject_path, metadata_fetcher=fetch_metadata)

    # Then: a formally released base version cannot receive a dev release


def test_resolve_testpypi_release_no_history_valid_return_dev1(tmp_path: Path) -> None:
    """An empty TestPyPI project receives the first development version"""
    # Given: a valid project and empty package index metadata
    pyproject_path = write_pyproject_version(tmp_path, "1.0.0")

    def fetch_empty_metadata(url: str) -> ReleaseIndexMetadata:
        return ReleaseIndexMetadata(())

    # When: the TestPyPI release is resolved
    resolution = resolve_testpypi_release(pyproject_path, metadata_fetcher=fetch_empty_metadata)

    # Then: the base and first development versions are returned
    assert resolution.base_version == Version("1.0.0")
    assert resolution.development_version == Version("1.0.0.dev1")


def test_read_project_base_version_missing_version_invalid_raise_ReleaseVersionError(tmp_path: Path) -> None:
    """Missing project.version metadata is rejected"""
    # Given: a pyproject.toml without project.version
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text('[project]\nname = "example"\n', encoding="utf-8")

    # When: the project base version is read
    with pytest.raises(ReleaseVersionError):
        read_project_base_version(pyproject_path)

    # Then: the workflow cannot continue without a base version
