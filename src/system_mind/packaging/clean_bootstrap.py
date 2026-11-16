"""Automated packaging validator auditing clean-clone bootstrap repeatability and setup results."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class CleanBootstrapAuditResult:
    """Outcome of auditing clean-clone bootstrap infrastructure and setup reports."""

    valid: bool
    issues: tuple[str, ...]
    report_valid: bool
    manifests_valid: bool
    verifier_cli_valid: bool
    milestone_freeze_valid: bool


class CleanBootstrapValidator:
    """Programmatic validator verifying clean-clone bootstrap reproducibility and setup reports."""

    REPORT_REL_PATH = Path("docs") / "records" / "CLEAN_CLONE_BOOTSTRAP_REPORT.md"
    CLI_REL_PATH = Path("tools") / "clean_clone_verifier.py"

    REQUIRED_REPORT_SECTIONS = [
        "## 1. Executive Summary",
        "## 2. Host Environment & Toolchain Inventory",
        "## 3. Monorepo Zone Manifests Verification",
        "## 4. Clean-Clone Bootstrap Execution Telemetry",
        "## 5. Security & Isolation Invariant Audit",
        "## 6. Milestone 3 Foundation Freeze & Sign-Off",
    ]

    REQUIRED_MANIFESTS = [
        "monorepo.json",
        "pyproject.toml",
        "Cargo.toml",
        "apps/desktop/package.json",
        "requirements.txt",
        "requirements-dev.txt",
        ".env.example",
        ".gitignore",
        ".github/workflows/ci.yml",
        ".github/workflows/dependency-review.yml",
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> CleanBootstrapAuditResult:
        """Executes full audit across report completeness, manifests, verifier CLI, and Milestone 3 freeze."""
        base_dir = root_dir or ROOT_DIR
        issues: List[str] = []
        report_ok = True
        manifests_ok = True
        cli_ok = True
        freeze_ok = True

        # 1. Audit Report Existence & Section Completeness
        report_path = base_dir / cls.REPORT_REL_PATH
        if not report_path.exists():
            issues.append(f"Missing clean-clone bootstrap report: {cls.REPORT_REL_PATH}")
            report_ok = False
        else:
            content = report_path.read_text(encoding="utf-8")
            if "Overall Status:** `PASSED`" not in content:
                issues.append("Bootstrap report does not record `PASSED` overall status")
                report_ok = False
            for sec in cls.REQUIRED_REPORT_SECTIONS:
                if sec not in content:
                    issues.append(f"Bootstrap report missing required section: {sec}")
                    report_ok = False

            # Check Milestone 3 sign-off checkboxes (Day 026 to Day 040)
            for day_idx in range(26, 41):
                day_token = f"Day {day_idx:03d}:"
                if day_token not in content:
                    issues.append(f"Bootstrap report Milestone 3 sign-off missing {day_token}")
                    freeze_ok = False

        # 2. Audit Monorepo Manifests
        for rel_manifest in cls.REQUIRED_MANIFESTS:
            m_path = base_dir / rel_manifest
            if not m_path.exists():
                issues.append(f"Missing required manifest for clean clone: {rel_manifest}")
                manifests_ok = False

        # 3. Audit Verifier CLI Tool
        cli_path = base_dir / cls.CLI_REL_PATH
        if not cli_path.exists():
            issues.append(f"Missing clean-clone verifier tool: {cls.CLI_REL_PATH}")
            cli_ok = False
        else:
            try:
                proc = subprocess.run(
                    [sys.executable, str(cli_path), "--dry-run", "--json"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                    cwd=str(base_dir),
                )
                if proc.returncode != 0:
                    issues.append(
                        f"clean_clone_verifier.py failed in dry-run with code {proc.returncode}: {proc.stderr}"
                    )
                    cli_ok = False
                else:
                    data = json.loads(proc.stdout)
                    if data.get("overall_status") != "PASSED":
                        issues.append(f"clean_clone_verifier.py reported overall_status '{data.get('overall_status')}'")
                        cli_ok = False
            except Exception as exc:
                issues.append(f"Error executing clean_clone_verifier.py: {exc}")
                cli_ok = False

        overall_valid = report_ok and manifests_ok and cli_ok and freeze_ok and (len(issues) == 0)
        return CleanBootstrapAuditResult(
            valid=overall_valid,
            issues=tuple(issues),
            report_valid=report_ok,
            manifests_valid=manifests_ok,
            verifier_cli_valid=cli_ok,
            milestone_freeze_valid=freeze_ok,
        )
