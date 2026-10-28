"""Regression tests for authorization in rerunnable release jobs."""

import os
import subprocess
from pathlib import Path

import pytest

from tests.unit.release.workflow_test_helpers import read_workflow_job, read_workflow_step_script

AUTHORIZATION_STEP = "Revalidate release authorization"
RELEASE_JOB_DEPENDENCIES = [
    ("publish-pypi.yml", "build", None, None),
    ("publish-pypi.yml", "publish", "build", "build"),
    ("publish-pypi.yml", "finalize", "[build, publish]", "publish"),
    ("finalize-github-release.yml", "finalize", None, None),
]
RELEASE_JOBS = [
    ("publish-pypi.yml", "build"),
    ("publish-pypi.yml", "publish"),
    ("finalize-github-release.yml", "finalize"),
]


@pytest.mark.parametrize("workflow_name,job_name", RELEASE_JOBS)
def test_release_authorization_first_step_valid_return_unconditional_check(workflow_name: str, job_name: str) -> None:
    """Every job starts with unconditional authorization before any release work"""
    # Given: a job that can be rerun independently of successful authorization jobs
    job = read_workflow_job(workflow_name, job_name)
    steps = job.split("    steps:\n", 1)[1]

    # When: the first step and its actor bindings are inspected
    first_step = steps.split("\n      - ", 1)[0]

    # Then: authorization cannot be skipped or ignored on any run attempt
    assert first_step.startswith(f"      - name: {AUTHORIZATION_STEP}\n")
    assert "INITIAL_ACTOR: ${{ github.actor }}" in first_step
    assert "TRIGGERING_ACTOR: ${{ github.triggering_actor }}" in first_step
    assert "GH_TOKEN: ${{ github.token }}" in first_step
    assert "        if:" not in first_step
    assert "continue-on-error:" not in first_step and "continue-on-error:" not in job.split("    steps:\n", 1)[0]


@pytest.mark.parametrize("workflow_name,job_name,expected_needs,required_success", RELEASE_JOB_DEPENDENCIES)
def test_release_job_dependencies_direct_valid_return_only_release_jobs(
    workflow_name: str, job_name: str, expected_needs: str | None, required_success: str | None
) -> None:
    """Release jobs depend only on the release work they require"""
    # Given: a release job and its expected direct dependencies
    job = read_workflow_job(workflow_name, job_name)
    header = job.split("    steps:\n", 1)[0]

    # When: the job dependencies and conditions are inspected
    needs = [line.strip() for line in header.splitlines() if line.startswith("    needs:")]

    # Then: authorization runs inside the job rather than as a dependency
    assert needs == ([f"needs: {expected_needs}"] if expected_needs is not None else [])
    assert "needs.authorize" not in header
    if required_success is None:
        assert "    if:" not in header
    else:
        assert "github.ref == 'refs/heads/main'" in header
        assert f"needs.{required_success}.result == 'success'" in header


@pytest.fixture
def authorization_environment(tmp_path: Path) -> dict[str, str]:
    """Provide a fake permission API without passing real credentials to tests

    Args:
        tmp_path (Path): Temporary directory for the fake curl executable

    Returns:
        dict[str, str]: Environment containing only mock authentication data
    """
    curl = tmp_path / "curl"
    curl.write_text(
        '#!/bin/bash\nset -euo pipefail\nurl="${!#}"\n'
        'printf "%s\\n" "$url" >> "$API_CALLS"\n'
        'case "$url" in\n'
        '  */initial-admin/permission) permission="$INITIAL_PERMISSION" ;;\n'
        '  */rerun-user/permission) permission="$TRIGGERING_PERMISSION" ;;\n'
        "  *) exit 1 ;;\n"
        "esac\n"
        'case "$permission" in\n'
        "  api-error) exit 22 ;;\n"
        '  malformed) echo "invalid JSON" ;;\n'
        '  missing) echo "{}" ;;\n'
        '  *) printf \'{"permission":"%s"}\\n\' "$permission" ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    curl.chmod(0o700)
    return {
        "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "dummy-test-token",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_API_URL": "https://api.invalid",
        "GITHUB_REPOSITORY": "example/repository",
        "INITIAL_ACTOR": "initial-admin",
        "TRIGGERING_ACTOR": "rerun-user",
        "INITIAL_PERMISSION": "admin",
        "TRIGGERING_PERMISSION": "admin",
        "API_CALLS": str(tmp_path / "api-calls.log"),
    }


@pytest.mark.parametrize("workflow_job", RELEASE_JOBS)
@pytest.mark.parametrize(
    "overrides,expected_code,expected_lookups",
    [
        ({}, 0, ["initial-admin", "rerun-user"]),
        ({"TRIGGERING_PERMISSION": "write"}, 1, ["initial-admin", "rerun-user"]),
        ({"INITIAL_PERMISSION": "write"}, 1, ["initial-admin"]),
        ({"TRIGGERING_PERMISSION": "api-error"}, 1, ["initial-admin", "rerun-user"]),
        ({"INITIAL_PERMISSION": "api-error"}, 1, ["initial-admin"]),
        ({"TRIGGERING_PERMISSION": "missing"}, 1, ["initial-admin", "rerun-user"]),
        ({"TRIGGERING_PERMISSION": "malformed"}, 1, ["initial-admin", "rerun-user"]),
        ({"GITHUB_REF": "refs/heads/other"}, 1, []),
    ],
)
def test_release_authorization_actor_permissions_edge_return_fail_closed(
    authorization_environment: dict[str, str],
    workflow_job: tuple[str, str],
    overrides: dict[str, str],
    expected_code: int,
    expected_lookups: list[str],
) -> None:
    """Each attempt checks both actors and stops on unauthorized or unknown state"""
    # Given: a new triggering actor, independent of previous successful job outputs
    workflow_name, job_name = workflow_job
    script = read_workflow_step_script(workflow_name, job_name, AUTHORIZATION_STEP)
    environment = authorization_environment | overrides

    # When: the workflow's actual shell step queries the fake permission API
    result = subprocess.run(["/bin/bash"], input=script, env=environment, capture_output=True, text=True, check=False)

    # Then: only administrators on main proceed; API failures also stop the job
    assert result.returncode == expected_code, result.stderr
    calls_path = Path(environment["API_CALLS"])
    calls = calls_path.read_text(encoding="utf-8").splitlines() if calls_path.exists() else []
    assert calls == [
        f"https://api.invalid/repos/example/repository/collaborators/{actor}/permission" for actor in expected_lookups
    ]
