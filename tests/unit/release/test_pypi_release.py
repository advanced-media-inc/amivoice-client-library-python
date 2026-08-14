"""Tests for formal PyPI release validation."""

import json
from pathlib import Path
from urllib.error import HTTPError

import pytest
from packaging.version import Version

from tools.release.pypi_release import (
    PyPIFileMetadata,
    PyPIIndexMetadata,
    PyPIReleaseError,
    ReleaseManifest,
    calculate_file_sha256,
    determine_pypi_release_state,
    fetch_pypi_index,
    find_latest_formal_version,
    read_release_manifest,
    validate_formal_release_version,
    validate_project_release_version,
    verify_local_release_manifest,
    verify_pypi_release,
)


class FakePyPIResponse:
    """Provide the response interface used by the PyPI JSON reader"""

    def __init__(self, payload: object, status_code: int = 200) -> None:
        """Create a fake response with a JSON body"""
        self._body = json.dumps(payload).encode()
        self.status = status_code

    def __enter__(self) -> "FakePyPIResponse":
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
    """Create a project metadata file for formal version tests"""
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(f'[project]\nname = "example"\nversion = "{version}"\n', encoding="utf-8")
    return pyproject_path


def create_manifest() -> ReleaseManifest:
    """Create a two-file manifest for PyPI state tests"""
    return ReleaseManifest(
        "amivoice-api-client",
        "1.1.0",
        {
            "amivoice_api_client-1.1.0-py3-none-any.whl": "a" * 64,
            "amivoice_api_client-1.1.0.tar.gz": "b" * 64,
        },
    )


def create_index(*files: PyPIFileMetadata, version: str = "1.1.0") -> PyPIIndexMetadata:
    """Create PyPI metadata with the requested files"""
    return PyPIIndexMetadata({version: tuple(files)})


def test_validate_formal_release_version_public_valid_return_version() -> None:
    """A canonical formal version is accepted"""
    # Given: a supported formal release version
    raw_version = "0.1.0"

    # When: the formal version is validated
    version = validate_formal_release_version(raw_version)

    # Then: the parsed version is returned
    assert version == Version("0.1.0")


@pytest.mark.parametrize("raw_version", ["0.0.1", "1.0.0.dev1", "1.0.0rc1", "1.0.0.post1", "1.0.0+local", "1.0"])
def test_validate_formal_release_version_non_formal_invalid_raise_PyPIReleaseError(raw_version: str) -> None:
    """Development, prerelease, post, local, and old versions are rejected"""
    # Given: a version that cannot be a formal PyPI release

    # When: the formal version is validated
    with pytest.raises(PyPIReleaseError):
        validate_formal_release_version(raw_version)

    # Then: the release workflow stops before building


def test_validate_project_release_version_mismatch_invalid_raise_PyPIReleaseError(tmp_path: Path) -> None:
    """The workflow input must match project.version"""
    # Given: project metadata with a different formal version
    pyproject_path = write_pyproject_version(tmp_path, "1.0.0")

    # When: a different workflow version is validated
    with pytest.raises(PyPIReleaseError):
        validate_project_release_version(pyproject_path, "1.1.0")

    # Then: a mismatched release cannot be built


def test_find_latest_formal_version_mixed_releases_valid_return_highest_formal() -> None:
    """Only canonical formal versions participate in latest-version comparison"""
    # Given: formal, development, prerelease, post, and local versions
    index_metadata = PyPIIndexMetadata(
        {
            "1.0.0": (),
            "1.1.0": (),
            "2.0.0.dev1": (),
            "2.0.0rc1": (),
            "1.1.0.post1": (),
            "1.1.0+local": (),
        }
    )

    # When: the latest formal version is found
    latest_version = find_latest_formal_version(index_metadata)

    # Then: only 1.1.0 is considered the latest formal release
    assert latest_version == Version("1.1.0")


def test_determine_pypi_release_state_newer_missing_valid_return_publish_required() -> None:
    """A newer absent version requires a PyPI upload"""
    # Given: PyPI contains only an older formal release
    index_metadata = PyPIIndexMetadata({"1.0.0": ()})
    manifest = create_manifest()

    # When: the release state is determined
    state = determine_pypi_release_state(index_metadata, Version("1.1.0"), manifest)

    # Then: the new version must be uploaded
    assert state.publish_required is True
    assert state.latest_formal_version == Version("1.0.0")


def test_determine_pypi_release_state_identical_existing_valid_return_no_upload() -> None:
    """An identical existing release is treated as already published"""
    # Given: PyPI has exactly the files in the local manifest
    manifest = create_manifest()
    index_metadata = create_index(
        PyPIFileMetadata("amivoice_api_client-1.1.0-py3-none-any.whl", "a" * 64),
        PyPIFileMetadata("amivoice_api_client-1.1.0.tar.gz", "b" * 64),
    )

    # When: the release state is determined
    state = determine_pypi_release_state(index_metadata, Version("1.1.0"), manifest)

    # Then: the upload is skipped safely
    assert state.publish_required is False


def test_determine_pypi_release_state_different_existing_invalid_raise_PyPIReleaseError() -> None:
    """A same-version hash mismatch fails closed"""
    # Given: PyPI has a different artifact hash for the requested version
    manifest = create_manifest()
    index_metadata = create_index(
        PyPIFileMetadata("amivoice_api_client-1.1.0-py3-none-any.whl", "c" * 64),
        PyPIFileMetadata("amivoice_api_client-1.1.0.tar.gz", "b" * 64),
    )

    # When: the release state is determined
    with pytest.raises(PyPIReleaseError):
        determine_pypi_release_state(index_metadata, Version("1.1.0"), manifest)

    # Then: a different artifact is never overwritten


def test_determine_pypi_release_state_not_newer_invalid_raise_PyPIReleaseError() -> None:
    """An absent version that is not newer than PyPI is rejected"""
    # Given: PyPI already has a newer formal release
    index_metadata = PyPIIndexMetadata({"1.2.0": ()})
    manifest = create_manifest()

    # When: an older release is evaluated
    with pytest.raises(PyPIReleaseError):
        determine_pypi_release_state(index_metadata, Version("1.1.0"), manifest)

    # Then: the workflow does not publish an out-of-order version


def test_fetch_pypi_index_not_found_valid_return_empty() -> None:
    """An absent PyPI project is treated as an empty index"""

    # Given: the JSON API responds with HTTP 404
    def open_not_found(url: str, *, timeout: float) -> FakePyPIResponse:
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    # When: PyPI metadata is fetched
    index_metadata = fetch_pypi_index("https://pypi.org/pypi/example/json", opener=open_not_found)

    # Then: no releases are returned
    assert index_metadata == PyPIIndexMetadata({})


def test_fetch_pypi_index_valid_returns_file_hashes() -> None:
    """PyPI file names and SHA-256 digests are parsed"""
    # Given: a valid PyPI JSON API response
    payload = {
        "releases": {
            "1.1.0": [
                {"filename": "package.whl", "digests": {"sha256": "a" * 64}},
            ]
        }
    }

    def open_valid(url: str, *, timeout: float) -> FakePyPIResponse:
        return FakePyPIResponse(payload)

    # When: PyPI metadata is fetched
    index_metadata = fetch_pypi_index("https://pypi.org/pypi/example/json", opener=open_valid)

    # Then: the file metadata is returned
    assert index_metadata.releases["1.1.0"] == (PyPIFileMetadata("package.whl", "a" * 64),)


def test_fetch_pypi_index_invalid_hash_invalid_raise_PyPIReleaseError() -> None:
    """Malformed PyPI file hashes fail closed"""
    # Given: a PyPI JSON response with an invalid digest
    payload = {"releases": {"1.1.0": [{"filename": "package.whl", "digests": {"sha256": "bad"}}]}}

    def open_invalid(url: str, *, timeout: float) -> FakePyPIResponse:
        return FakePyPIResponse(payload)

    # When: PyPI metadata is fetched
    with pytest.raises(PyPIReleaseError):
        fetch_pypi_index("https://pypi.org/pypi/example/json", opener=open_invalid)

    # Then: release state cannot be inferred from malformed metadata


def test_write_and_read_release_manifest_valid_round_trip(tmp_path: Path) -> None:
    """A release manifest preserves file hashes and metadata"""
    # Given: a local artifact and a manifest path
    artifact_path = tmp_path / "artifact.whl"
    sdist_path = tmp_path / "artifact.tar.gz"
    artifact_path.write_bytes(b"wheel artifact")
    sdist_path.write_bytes(b"source artifact")
    manifest_path = tmp_path / "release-manifest.json"
    manifest = ReleaseManifest(
        "amivoice-api-client",
        "1.1.0",
        {
            artifact_path.name: calculate_file_sha256(artifact_path),
            sdist_path.name: calculate_file_sha256(sdist_path),
        },
    )
    manifest_path.write_text(
        json.dumps(
            {
                "distribution": manifest.distribution_name,
                "version": manifest.version,
                "files": [{"filename": filename, "sha256": sha256} for filename, sha256 in manifest.files.items()],
            }
        ),
        encoding="utf-8",
    )

    # When: the manifest is read
    loaded_manifest = read_release_manifest(manifest_path)

    # Then: the manifest metadata and digest are preserved
    assert loaded_manifest == manifest


def test_verify_local_release_manifest_matching_valid_returns_none(tmp_path: Path) -> None:
    """Local files matching a manifest pass verification"""
    # Given: a directory and manifest with the same file digest
    artifact_path = tmp_path / "artifact.whl"
    artifact_path.write_bytes(b"artifact")
    manifest = ReleaseManifest("amivoice-api-client", "1.1.0", {artifact_path.name: calculate_file_sha256(artifact_path)})

    # When: local artifact hashes are verified
    verify_local_release_manifest(tmp_path, manifest)

    # Then: no exception is raised


def test_verify_pypi_release_matching_valid_returns_none() -> None:
    """PyPI files matching a manifest pass verification"""
    # Given: PyPI metadata with the expected release files
    manifest = create_manifest()
    index_metadata = create_index(
        PyPIFileMetadata("amivoice_api_client-1.1.0-py3-none-any.whl", "a" * 64),
        PyPIFileMetadata("amivoice_api_client-1.1.0.tar.gz", "b" * 64),
    )

    # When: the published release is verified
    verify_pypi_release(index_metadata, manifest)

    # Then: no exception is raised
