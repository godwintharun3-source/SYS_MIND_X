"""Automated validator auditing GitHub Actions CI workflows, jobs, and dependency review configs."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

from system_mind.packaging.dependency_review import DependencyReviewer


@dataclass(frozen=True)
class CiChecksAuditResult:
    """Results of auditing CI workflows and dependency review infrastructure."""

    valid: bool
    issues: tuple[str, ...]
    workflows_valid: bool
    dependencies_valid: bool
    ci_runner_valid: bool


class CiChecksValidator:
    """Programmatic validator verifying CI workflow definitions and dependency reviews in CI."""

    REQUIRED_WORKFLOWS = [
        ".github/workflows/ci.yml",
        ".github/workflows/dependency-review.yml",
    ]

    REQUIRED_CI_JOBS = [
        "lint-and-safety",
        "test-python",
        "test-rust",
        "test-frontend",
        "database-migrations",
    ]

    @classmethod
    def audit(cls, root_dir: Path | None = None) -> CiChecksAuditResult:
        """Audits CI workflow files, required jobs, dependency reviews, and local CI runner."""
        base_dir = root_dir or ROOT_DIR
        issues: list[str] = []
        workflows_ok = True
        deps_ok = False
        runner_ok = False

        # 1. Audit workflow files existence and basic structure
        for rel_path in cls.REQUIRED_WORKFLOWS:
            workflow_file = base_dir / rel_path
            if not workflow_file.exists():
                issues.append(f"Missing required CI workflow: {rel_path}")
                workflows_ok = False
                continue

            content = workflow_file.read_text(encoding="utf-8")
            if "name:" not in content or "jobs:" not in content:
                issues.append(f"Malformed CI workflow structure in {rel_path}: missing name or jobs block.")
                workflows_ok = False

        # 2. Check required jobs in ci.yml
        ci_yml = base_dir / ".github/workflows/ci.yml"
        if ci_yml.exists():
            ci_content = ci_yml.read_text(encoding="utf-8")
            for job in cls.REQUIRED_CI_JOBS:
                if f"{job}:" not in ci_content:
                    issues.append(f".github/workflows/ci.yml missing required job: '{job}'")
                    workflows_ok = False

        # 3. Audit dependency review
        dep_result = DependencyReviewer.audit(base_dir)
        if not dep_result.valid:
            issues.extend(dep_result.issues)
            deps_ok = False
        else:
            deps_ok = True

        # 4. Audit local CI runner tool
        ci_runner_path = base_dir / "tools" / "ci_runner.py"
        if not ci_runner_path.exists():
            issues.append("Missing developer tool tools/ci_runner.py")
        else:
            if os.name != "nt" and not os.access(ci_runner_path, os.X_OK):
                issues.append("tools/ci_runner.py must have executable permissions (chmod +x).")

            # Run dry-run check
            try:
                proc = subprocess.run(
                    [sys.executable, str(ci_runner_path), "--dry-run", "--json", "all"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                )
                if proc.returncode != 0:
                    issues.append(f"tools/ci_runner.py --dry-run failed with code {proc.returncode}: {proc.stderr}")
                else:
                    runner_ok = True
            except Exception as e:
                issues.append(f"Failed to execute tools/ci_runner.py dry-run: {e}")

        valid = len(issues) == 0
        return CiChecksAuditResult(
            valid=valid,
            issues=tuple(issues),
            workflows_valid=workflows_ok,
            dependencies_valid=deps_ok,
            ci_runner_valid=runner_ok,
        )
