"""Helpers for testing shell steps directly from release workflows."""

from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[3] / ".github" / "workflows"


def read_workflow_job(workflow_name: str, job_name: str) -> str:
    """Read one top-level job from the repository workflow

    Args:
        workflow_name (str): Workflow filename
        job_name (str): Top-level job identifier

    Returns:
        str: The job body without subsequent jobs
    """
    workflow = (WORKFLOW_DIR / workflow_name).read_text(encoding="utf-8")
    lines = workflow.split(f"\n  {job_name}:\n", 1)[1].splitlines()
    job_lines: list[str] = []
    for line in lines:
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            break
        job_lines.append(line)
    return "\n".join(job_lines)


def read_workflow_step_script(workflow_name: str, job_name: str, step_name: str) -> str:
    """Extract a named literal shell script without adding a YAML dependency

    Args:
        workflow_name (str): Workflow filename
        job_name (str): Top-level job identifier
        step_name (str): Step display name

    Returns:
        str: The shell script stored in the run block
    """
    job = read_workflow_job(workflow_name, job_name)
    step = job.split(f"      - name: {step_name}\n", 1)[1].split("\n      - ", 1)[0]
    script_lines = step.split("        run: |\n", 1)[1].splitlines()
    assert all(not line.strip() or line.startswith("          ") for line in script_lines)
    return "\n".join(line[10:] for line in script_lines) + "\n"
