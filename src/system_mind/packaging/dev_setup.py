"""Automated validator auditing development setup scripts, prerequisites, and documentation."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class DevSetupAuditResult:
    """Results of auditing development setup infrastructure."""

    valid: bool
    issues: tuple[str, ...]
    required_files_present: bool
    prerequisites_valid: bool
    cleaner_bounded: bool


class DevSetupValidator:
    """Programmatic validator verifying development setup scripts and documentation in CI."""

    REQUIRED_FILES = [
        "docs/DEVELOPMENT_SETUP.md",
        "tools/dev_setup.py",
        "tools/setup_dev.sh",
        "tools/setup_dev.ps1",
        ".env.example",
    ]

    @classmethod
    def audit(cls, root_dir: Path | None = None) -> DevSetupAuditResult:
        """Audits development setup scripts, permissions, safety constraints, and cleaner bounds."""
        base_dir = root_dir or ROOT_DIR
        issues: list[str] = []
        files_ok = True
        prereqs_ok = False
        cleaner_ok = False

        # 1. Verify required files exist
        for rel_file in cls.REQUIRED_FILES:
            target = base_dir / rel_file
            if not target.exists():
                issues.append(f"Required setup file missing: {rel_file}")
                files_ok = False

        # 2. Verify executable permissions on unix scripts
        if os.name != "nt":
            for script_name in ["tools/dev_setup.py", "tools/setup_dev.sh"]:
                script_path = base_dir / script_name
                if script_path.exists() and not os.access(script_path, os.X_OK):
                    issues.append(f"Script {script_name} must have executable permissions (chmod +x).")

        # 3. Verify absence of sudo / privileged commands in shell scripts
        sh_script = base_dir / "tools" / "setup_dev.sh"
        if sh_script.exists():
            sh_content = sh_script.read_text(encoding="utf-8")
            exec_lines = [
                line.strip()
                for line in sh_content.splitlines()
                if not line.strip().startswith("#") and not line.strip().startswith("echo")
            ]
            if any(line.startswith("sudo ") for line in exec_lines):
                issues.append("Banned 'sudo' command invocation detected in tools/setup_dev.sh.")

        # 4. Import and test PrerequisiteChecker and WorkspaceCleaner
        tools_dir = base_dir / "tools"
        if str(tools_dir) not in sys.path:
            sys.path.insert(0, str(tools_dir))

        try:
            from dev_setup import PrerequisiteChecker, WorkspaceCleaner

            diag = PrerequisiteChecker.check_all()
            if "all_satisfied" not in diag or "tools" not in diag:
                issues.append("PrerequisiteChecker.check_all() returned malformed diagnostic schema.")
            else:
                prereqs_ok = True

            # Verify WorkspaceCleaner dry-run
            preview = WorkspaceCleaner.clean(dry_run=True)
            for item in preview:
                resolved = (base_dir / item).resolve()
                if base_dir not in resolved.parents and resolved != base_dir:
                    issues.append(f"WorkspaceCleaner unbounded path detected: {item}")
            cleaner_ok = True
        except Exception as e:
            issues.append(f"Failed to execute dev_setup internal checks: {e}")

        valid = len(issues) == 0
        return DevSetupAuditResult(
            valid=valid,
            issues=tuple(issues),
            required_files_present=files_ok,
            prerequisites_valid=prereqs_ok,
            cleaner_bounded=cleaner_ok,
        )
