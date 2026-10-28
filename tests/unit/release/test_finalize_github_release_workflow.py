"""Regression tests for the formal release tag shell step."""

import base64
import os
import subprocess
from pathlib import Path

import pytest

from tests.unit.release.workflow_test_helpers import read_workflow_step_script

SOURCE_COMMIT = "a" * 40


@pytest.fixture
def tag_environment(tmp_path: Path) -> dict[str, str]:
    """Provide a fake Git executable so tests cannot push to a remote

    Args:
        tmp_path (Path): Temporary directory for the fake executable and log

    Returns:
        dict[str, str]: Environment for the workflow shell step
    """
    git = tmp_path / "git"
    git.write_text(
        '#!/bin/bash\nset -euo pipefail\nprintf "%s\\n" "$*" >> "$GIT_CALLS"\n'
        'case "$1" in\n'
        '  show-ref) [[ -n "$EXISTING_TAG_COMMIT" ]] ;;\n'
        '  rev-list) printf "%s\\n" "$EXISTING_TAG_COMMIT" ;;\n'
        '  -c) echo "mock push" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    git.chmod(0o700)
    return {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "dummy-test-token",
        "RELEASE_VERSION": "1.0.0",
        "SOURCE_COMMIT": SOURCE_COMMIT,
        "EXISTING_TAG_COMMIT": "",
        "GIT_CALLS": str(tmp_path / "git-calls.log"),
    }


def test_release_tag_missing_valid_return_masked_basic_push(tag_environment: dict[str, str]) -> None:
    """A new tag uses a masked Basic credential for Git HTTPS authentication"""
    # Given: the actual workflow script and no existing release tag
    script = read_workflow_step_script("finalize-github-release.yml", "finalize", "Create or verify the immutable release tag")
    credential = base64.b64encode(f"x-access-token:{tag_environment['GH_TOKEN']}".encode()).decode()

    # When: the tag step executes against the fake Git executable
    result = subprocess.run(["/bin/bash"], input=script, env=tag_environment, capture_output=True, text=True, check=False)

    # Then: the credential is masked before pushing and is not persisted in Git config
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [f"::add-mask::{credential}", "mock push"]
    calls = Path(tag_environment["GIT_CALLS"]).read_text(encoding="utf-8").splitlines()
    assert f"-c http.extraheader=AUTHORIZATION: basic {credential} push origin refs/tags/1.0.0" in calls
    assert not any("bearer" in call.lower() or (call.startswith("config ") and "extraheader" in call) for call in calls)


@pytest.mark.parametrize("existing_commit,expected_code", [(SOURCE_COMMIT, 0), ("b" * 40, 1)])
def test_release_tag_existing_edge_return_without_push(
    tag_environment: dict[str, str], existing_commit: str, expected_code: int
) -> None:
    """Existing tags are accepted only for the exact source commit and never pushed"""
    # Given: an existing tag pointing to either the expected or a different commit
    tag_environment["EXISTING_TAG_COMMIT"] = existing_commit
    script = read_workflow_step_script("finalize-github-release.yml", "finalize", "Create or verify the immutable release tag")

    # When: the immutable tag is checked
    result = subprocess.run(["/bin/bash"], input=script, env=tag_environment, capture_output=True, text=True, check=False)

    # Then: only the matching tag succeeds and no remote write is attempted
    assert result.returncode == expected_code
    calls = Path(tag_environment["GIT_CALLS"]).read_text(encoding="utf-8").splitlines()
    assert not any(call.startswith(("tag ", "-c ")) for call in calls)
