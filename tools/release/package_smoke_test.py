"""Run import and metadata smoke tests against an installed package."""

import argparse
import sys
from importlib import metadata
from pathlib import Path

import com.amivoice.hrp as hrp_package
import com.amivoice.wrp as wrp_package

import amivoice
from amivoice import AmiVoiceClient


class PackageSmokeTestError(RuntimeError):
    """Indicate that an installed package failed its release smoke test"""


def run_package_smoke_test(distribution_name: str, expected_version: str) -> None:
    """Verify package metadata, public imports, and package typing marker

    Args:
        distribution_name: Installed distribution name to inspect
        expected_version: Exact expected distribution version

    Raises:
        PackageSmokeTestError: If an installed package check fails
    """
    try:
        installed_version = metadata.version(distribution_name)
    except metadata.PackageNotFoundError as error:
        raise PackageSmokeTestError(f"Installed distribution was not found: {distribution_name}") from error
    if installed_version != expected_version:
        raise PackageSmokeTestError(f"Installed distribution version mismatch: {installed_version} != {expected_version}")

    imported_packages = (amivoice, hrp_package, wrp_package)
    expected_module_names = {"amivoice", "com.amivoice.hrp", "com.amivoice.wrp"}
    if {package.__name__ for package in imported_packages} != expected_module_names:
        raise PackageSmokeTestError("One or more public package imports failed")

    amivoice_package_root = Path(next(iter(amivoice.__path__)))
    if not (amivoice_package_root / "py.typed").is_file():
        raise PackageSmokeTestError("Installed package does not contain amivoice/py.typed")

    client = AmiVoiceClient(api_key="package-smoke-test")
    if not callable(client.transcribe) or not callable(client.stream):
        raise PackageSmokeTestError("AmiVoiceClient public methods are not callable")


def _parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an installed package smoke test")
    parser.add_argument("--distribution", default="amivoice-api-client", help="Installed distribution name")
    parser.add_argument("--version", required=True, help="Expected installed package version")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    """Run the installed package smoke test command line interface

    Args:
        arguments: Optional command line arguments for testing

    Returns:
        Zero when the smoke test passes and one otherwise
    """
    parsed_arguments = _parse_arguments(arguments)
    try:
        run_package_smoke_test(parsed_arguments.distribution, parsed_arguments.version)
    except PackageSmokeTestError as error:
        print(f"Package smoke test failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
