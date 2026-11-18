"""Comprehensive unit, integration, and contract tests for Clean-Clone Bootstrap verification."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent

from system_mind.packaging.clean_bootstrap import (
    CleanBootstrapAuditResult,
    CleanBootstrapValidator,
)
from tools.clean_clone_verifier import (
    CleanCloneVerifier,
    run_command_safely,
)


def test_clean_bootstrap_report_existence_and_sections():
    """Verify that the official clean-clone bootstrap report exists and contains all required sections."""
    report_path = ROOT_DIR / "docs" / "records" / "CLEAN_CLONE_BOOTSTRAP_REPORT.md"
    assert report_path.exists(), f"Bootstrap report missing at {report_path}"

    content = report_path.read_text(encoding="utf-8")
    assert "Overall Status:** `PASSED`" in content
    assert "Milestone 3: Repository and development foundation (Days 026–040)" in content

    for section in CleanBootstrapValidator.REQUIRED_REPORT_SECTIONS:
        assert section in content, f"Missing required section: {section}"


def test_clean_bootstrap_report_milestone_3_freeze_completeness():
    """Verify that the report documents sign-off for all 15 days of Milestone 3."""
    report_path = ROOT_DIR / "docs" / "records" / "CLEAN_CLONE_BOOTSTRAP_REPORT.md"
    content = report_path.read_text(encoding="utf-8")

    for day in range(26, 41):
        token = f"[x] **Day {day:03d}:**"
        assert token in content, f"Milestone 3 sign-off missing confirmation for Day {day:03d}"


def test_clean_clone_verifier_manifests_check():
    """Verify CleanCloneVerifier validates all root monorepo manifests."""
    manifest_results = CleanCloneVerifier.verify_manifests()
    assert manifest_results["all_manifests_present"] is True

    manifests = manifest_results["manifests"]
    for rel_path in CleanCloneVerifier.REQUIRED_MANIFESTS:
        assert rel_path in manifests
        assert manifests[rel_path]["present"] is True
        assert manifests[rel_path]["size_bytes"] > 0


def test_clean_clone_verifier_environment_inspection():
    """Verify CleanCloneVerifier inspects host environment facts truthfully."""
    env = CleanCloneVerifier.inspect_environment()
    assert env["os_name"] != ""
    assert env["architecture"] in ("arm64", "x86_64", "aarch64", "amd64")
    assert env["cpu_cores"] >= 1
    assert env["memory_bytes"] > 0
    assert "python3" in env["installed_tools"]
    assert env["installed_tools"]["python3"] is not None


def test_clean_clone_verifier_cli_dry_run_json():
    """Verify clean_clone_verifier.py CLI works in dry-run with structured JSON output."""
    cli_path = ROOT_DIR / "tools" / "clean_clone_verifier.py"

    code, out, err = run_command_safely([sys.executable, str(cli_path), "--dry-run", "--json"])
    assert code == 0, f"clean_clone_verifier.py failed: {err}"

    data = json.loads(out)
    assert data["overall_status"] == "PASSED"
    assert data["dry_run"] is True
    assert len(data["stages"]) == 8
    for stage in data["stages"]:
        assert stage["status"] == "PASSED"
        assert stage["exit_code"] == 0


def test_clean_clone_verifier_cli_live_custom_report():
    """Verify clean_clone_verifier.py can execute and render to an isolated custom report path."""
    cli_path = ROOT_DIR / "tools" / "clean_clone_verifier.py"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_report = Path(tmp_dir) / "test_report.md"
        code, out, err = run_command_safely(
            [sys.executable, str(cli_path), "--dry-run", "--report", str(tmp_report)]
        )
        assert code == 0, f"Failed rendering to custom report: {err}"
        assert tmp_report.exists()
        assert "SYSTEM MIND X — Clean-Clone Bootstrap & Setup Report" in tmp_report.read_text(encoding="utf-8")


def test_clean_bootstrap_validator_audits_clean():
    """Verify CleanBootstrapValidator passes clean audit of the repository bootstrap infrastructure."""
    audit_result = CleanBootstrapValidator.audit()
    assert audit_result.valid is True, f"CleanBootstrapValidator audit failed: {audit_result.issues}"
    assert audit_result.report_valid is True
    assert audit_result.manifests_valid is True
    assert audit_result.verifier_cli_valid is True
    assert audit_result.milestone_freeze_valid is True
    assert len(audit_result.issues) == 0


def test_clean_clone_unprivileged_invariant():
    """Verify setup and bootstrap tools contain zero executable sudo invocations."""
    setup_scripts = [
        ROOT_DIR / "tools" / "clean_clone_verifier.py",
        ROOT_DIR / "tools" / "dev_setup.py",
        ROOT_DIR / "tools" / "setup_dev.sh",
        ROOT_DIR / "tools" / "setup_dev.ps1",
    ]

    for script in setup_scripts:
        assert script.exists(), f"Missing setup script: {script}"
        content = script.read_text(encoding="utf-8")
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()
            # Ignore comments and echo/warning lines
            if stripped.startswith("#") or stripped.startswith("echo") or stripped.startswith("Write-"):
                continue
            assert not stripped.startswith("sudo "), (
                f"Forbidden sudo command detected in {script.name}:{idx}: {stripped}"
            )


def test_clean_clone_isolated_database_lifecycle():
    """Verify that SQLite migrations apply and verify cleanly on a fresh isolated database file."""
    migrate_py = ROOT_DIR / "tools" / "migrate.py"

    with tempfile.TemporaryDirectory() as tmp_dir:
        isolated_db = Path(tmp_dir) / "isolated_clean.db"

        # Apply migrations
        code, out, err = run_command_safely(
            [sys.executable, str(migrate_py), "--db", str(isolated_db), "--json", "apply"]
        )
        assert code == 0, f"Migration apply failed: {err}"
        assert isolated_db.exists()

        # Verify integrity
        code, out, err = run_command_safely(
            [sys.executable, str(migrate_py), "--db", str(isolated_db), "--json", "verify"]
        )
        assert code == 0, f"Migration verify failed: {err}"
        verify_data = json.loads(out)
        assert verify_data["valid"] is True
        assert verify_data["applied_count"] >= 2
        assert verify_data["latest_version"] >= 2
