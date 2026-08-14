"""Tests for temporary TestPyPI source preparation."""

import tomllib
from pathlib import Path

import pytest

from tools.release.prepare_testpypi_source import PyPITestSourceError, prepare_testpypi_source


def create_source_tree(tmp_path: Path) -> Path:
    """Create a minimal source tree with files that should and should not be copied"""
    source_root = tmp_path / "source"
    (source_root / "src" / "amivoice").mkdir(parents=True)
    (source_root / "dist").mkdir()
    (source_root / ".git").mkdir()
    (source_root / "src" / "amivoice_api_client.egg-info").mkdir(parents=True)
    (source_root / "pyproject.toml").write_text(
        '[project]\nname = "amivoice-api-client"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (source_root / "README.md").write_text("readme\n", encoding="utf-8")
    (source_root / "src" / "amivoice" / "py.typed").write_text("", encoding="utf-8")
    (source_root / "dist" / "old.whl").write_text("old\n", encoding="utf-8")
    (source_root / ".git" / "config").write_text("git\n", encoding="utf-8")
    (source_root / "src" / "amivoice_api_client.egg-info" / "PKG-INFO").write_text("metadata\n", encoding="utf-8")
    return source_root


def test_prepare_testpypi_source_valid_creates_versioned_copy(tmp_path: Path) -> None:
    """The copied project receives only the requested development version"""
    # Given: a source tree with generated and repository metadata files
    source_root = create_source_tree(tmp_path)
    destination_root = tmp_path / "prepared"

    # When: a TestPyPI source tree is prepared
    prepared_root = prepare_testpypi_source(source_root, destination_root, "0.1.0", "0.1.0.dev1")

    # Then: the copied project has the development version
    with (prepared_root / "pyproject.toml").open("rb") as pyproject_file:
        project = tomllib.load(pyproject_file)["project"]
    assert project["version"] == "0.1.0.dev1"
    assert (prepared_root / "README.md").is_file()
    assert (prepared_root / "src" / "amivoice" / "py.typed").is_file()
    assert not (prepared_root / "dist").exists()
    assert not (prepared_root / ".git").exists()
    assert not (prepared_root / "src" / "amivoice_api_client.egg-info").exists()


def test_prepare_testpypi_source_base_mismatch_invalid_raise_PyPITestSourceError(tmp_path: Path) -> None:
    """A copied project whose version differs from the resolved base is rejected"""
    # Given: a source tree with a different project version
    source_root = create_source_tree(tmp_path)

    # When: a mismatched base version is used
    with pytest.raises(PyPITestSourceError):
        prepare_testpypi_source(source_root, tmp_path / "prepared", "1.1.0", "1.1.0.dev1")

    # Then: no temporary source tree is left behind
    assert not (tmp_path / "prepared").exists()


@pytest.mark.parametrize("development_version", ["0.1.0", "0.1.0rc1", "0.1.0.dev01", "0.2.0.dev1", "0.1.0.dev1+local"])
def test_prepare_testpypi_source_non_development_version_invalid_raise_PyPITestSourceError(
    tmp_path: Path, development_version: str
) -> None:
    """A TestPyPI source tree requires an exact development version"""
    # Given: a valid project source tree
    source_root = create_source_tree(tmp_path)

    # When: an invalid development version is requested
    with pytest.raises(PyPITestSourceError):
        prepare_testpypi_source(source_root, tmp_path / "prepared", "0.1.0", development_version)

    # Then: no copy is created
    assert not (tmp_path / "prepared").exists()
