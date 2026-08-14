"""Create a temporary source tree with a TestPyPI development version."""

import argparse
import re
import shutil
import tomllib
from collections.abc import Iterable
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .testpypi_version import ReleaseVersionError, validate_base_version

IGNORED_SOURCE_NAMES = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "build",
        "dist",
        "node_modules",
    }
)
PROJECT_VERSION_LINE = re.compile(r'(?m)^version\s*=\s*"[^"\n]+"\s*$')


class PyPITestSourceError(ValueError):
    """Indicate that a temporary TestPyPI source tree cannot be created"""


def _ignore_source_files(directory: str, names: Iterable[str]) -> set[str]:
    del directory
    return {name for name in names if name in IGNORED_SOURCE_NAMES or name.endswith(".egg-info")}


def _validate_development_version(base_version: Version, raw_version: str) -> Version:
    try:
        development_version = Version(raw_version)
    except InvalidVersion as error:
        raise PyPITestSourceError("TestPyPI version is not a valid PEP 440 version") from error

    if (
        str(development_version) != raw_version
        or not development_version.is_devrelease
        or development_version.release != base_version.release
        or development_version.post is not None
        or development_version.local is not None
    ):
        raise PyPITestSourceError("TestPyPI version must be the exact base-version.devN format")

    return development_version


def _replace_project_version(pyproject_path: Path, base_version: Version, development_version: Version) -> None:
    try:
        with pyproject_path.open("rb") as pyproject_file:
            project_metadata = tomllib.load(pyproject_file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PyPITestSourceError(f"Unable to read copied project metadata: {pyproject_path}") from error

    project = project_metadata.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("version"), str):
        raise PyPITestSourceError("Copied project metadata does not contain project.version")
    try:
        copied_base_version = validate_base_version(project["version"])
    except ReleaseVersionError as error:
        raise PyPITestSourceError("Copied project version is not a valid public base version") from error
    if copied_base_version != base_version:
        raise PyPITestSourceError("Copied project version does not match the resolved base version")

    original_text = pyproject_path.read_text(encoding="utf-8")
    updated_text, replacements = PROJECT_VERSION_LINE.subn(f'version = "{development_version}"', original_text)
    if replacements != 1:
        raise PyPITestSourceError("Copied project metadata must contain exactly one project version line")
    pyproject_path.write_text(updated_text, encoding="utf-8")


def prepare_testpypi_source(
    source_root: Path,
    destination_root: Path,
    base_version_text: str,
    development_version_text: str,
) -> Path:
    """Copy a project and change only the copied project version

    Args:
        source_root: Repository root to copy
        destination_root: Empty path for the temporary source tree
        base_version_text: Expected public project version
        development_version_text: Exact TestPyPI development version

    Returns:
        The path to the prepared source tree

    Raises:
        PyPITestSourceError: If validation or copying fails
    """
    try:
        base_version = validate_base_version(base_version_text)
        development_version = _validate_development_version(base_version, development_version_text)
    except (OSError, ValueError) as error:
        if isinstance(error, PyPITestSourceError):
            raise
        raise PyPITestSourceError(str(error)) from error

    if not source_root.is_dir():
        raise PyPITestSourceError(f"Source root does not exist: {source_root}")
    if destination_root.exists():
        raise PyPITestSourceError(f"Destination already exists: {destination_root}")

    try:
        shutil.copytree(source_root, destination_root, ignore=_ignore_source_files)
        _replace_project_version(destination_root / "pyproject.toml", base_version, development_version)
    except (OSError, PyPITestSourceError):
        shutil.rmtree(destination_root, ignore_errors=True)
        raise

    return destination_root


def _parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a temporary TestPyPI source tree")
    parser.add_argument("--source", type=Path, default=Path.cwd(), help="Repository root to copy")
    parser.add_argument("--destination", type=Path, required=True, help="Destination path for the copied source")
    parser.add_argument("--base-version", required=True, help="Expected public project version")
    parser.add_argument("--version", required=True, help="Exact TestPyPI development version")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run the temporary TestPyPI source preparation command line interface

    Args:
        arguments: Optional command line arguments for testing

    Returns:
        Zero after creating the source tree and one on validation failure
    """
    parsed_arguments = _parse_arguments(arguments)
    try:
        prepare_testpypi_source(
            parsed_arguments.source,
            parsed_arguments.destination,
            parsed_arguments.base_version,
            parsed_arguments.version,
        )
    except PyPITestSourceError as error:
        print(f"TestPyPI source preparation failed: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
