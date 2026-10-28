"""Regression tests for release workflow summaries."""

import os
import subprocess
from pathlib import Path

import pytest

from tests.unit.release.workflow_test_helpers import read_workflow_step_script


@pytest.mark.parametrize(
    "workflow_name,job_name,step_name,expected_lines",
    [
        (
            "publish-pypi.yml",
            "build",
            "Write build summary",
            ["- Version: `1.2.3`", "- Upload required: `true`"],
        ),
        (
            "publish-pypi.yml",
            "publish",
            "Write publication summary",
            ["- Version: `1.2.3`", "- Upload performed: `true`"],
        ),
        (
            "finalize-github-release.yml",
            "finalize",
            "Write finalization summary",
            ["- Version: `1.2.3`", f"- Source commit: `{'a' * 40}`"],
        ),
        (
            "publish-testpypi.yml",
            "build",
            "Write build summary",
            ["- Base version: `1.2.3`", "- Development version: `1.2.3.dev1`"],
        ),
        (
            "publish-testpypi.yml",
            "publish",
            "Write publication summary",
            ["Published `amivoice-api-client==1.2.3.dev1`"],
        ),
        (
            "publish-testpypi.yml",
            "smoke-test",
            "Write smoke test summary",
            ["Verified `amivoice-api-client==1.2.3.dev1`"],
        ),
    ],
)
def test_release_summary_values_valid_return_markdown(
    tmp_path: Path, workflow_name: str, job_name: str, step_name: str, expected_lines: list[str]
) -> None:
    """Summary values are written as Markdown instead of executed as commands"""
    # Given: the actual workflow step and a local distribution for hash summaries
    summary_path = tmp_path / "summary.md"
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "example.whl").write_bytes(b"test artifact")
    environment = {
        "PATH": os.environ["PATH"],
        "GITHUB_STEP_SUMMARY": str(summary_path),
        "RELEASE_VERSION": "1.2.3",
        "PUBLISH_REQUIRED": "true",
        "SOURCE_COMMIT": "a" * 40,
        "BASE_VERSION": "1.2.3",
        "DEVELOPMENT_VERSION": "1.2.3.dev1",
        "DISTRIBUTION_NAME": "amivoice-api-client",
    }
    script = read_workflow_step_script(workflow_name, job_name, step_name)

    # When: the step runs with the GitHub Actions shell options
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-e", "-o", "pipefail"],
        input=script,
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: each value is preserved inside literal Markdown backticks
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    summary = summary_path.read_text(encoding="utf-8")
    assert all(line in summary.splitlines() for line in expected_lines)
