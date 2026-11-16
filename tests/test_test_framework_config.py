"""Unit and contract tests for polyglot test framework configurations and test runner CLI."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

from system_mind.packaging import (
    TestFrameworkAuditResult,
    TestFrameworkValidator,
)


def test_test_framework_validator_audits_clean():
    """Verify that current repository test framework configuration passes all audit criteria."""
    result = TestFrameworkValidator.audit_test_framework()

    assert result.is_valid is True
    assert len(result.issues) == 0
    assert result.missing_pytest_markers == []

    # Verify all 5 markers registered
    for req_marker in ["unit", "integration", "e2e", "contract", "safety_critical"]:
        assert req_marker in result.registered_pytest_markers

    assert result.integration_tests_verified is True
    assert result.e2e_tests_verified is True
    assert result.rust_integration_tests_verified is True
    assert result.frontend_test_config_verified is True
    assert result.test_runner_cli_verified is True


def test_test_framework_validator_detects_missing_markers():
    """Verify that validator catches missing pytest markers or missing strict-markers."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Incomplete pyproject.toml
        pyproject_content = """
[tool.pytest.ini_options]
addopts = "-v"
markers = [
    "unit: Unit tests",
]
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content)

        result = TestFrameworkValidator.audit_test_framework(tmp_path)
        assert result.is_valid is False
        assert "integration" in result.missing_pytest_markers
        assert "e2e" in result.missing_pytest_markers
        assert "contract" in result.missing_pytest_markers
        assert "safety_critical" in result.missing_pytest_markers
        assert any("--strict-markers" in issue for issue in result.issues)


def test_test_framework_validator_detects_missing_test_files():
    """Verify that validator flags missing test files across tiers."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Complete pyproject.toml but no test files
        pyproject_content = """
[tool.pytest.ini_options]
addopts = "-v --strict-markers"
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "e2e: E2E tests",
    "contract: Contract tests",
    "safety_critical: Charter safety tests",
]
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content)

        result = TestFrameworkValidator.audit_test_framework(tmp_path)
        assert result.is_valid is False
        assert result.integration_tests_verified is False
        assert result.e2e_tests_verified is False
        assert result.rust_integration_tests_verified is False
        assert any("test_integration_pipeline.py" in issue for issue in result.issues)


def test_test_runner_cli_execution():
    """Verify that tools/test_runner.py executes successfully for targeted suites."""
    root_dir = Path(__file__).resolve().parent.parent
    runner_path = root_dir / "tools" / "test_runner.py"

    # Test running only integration suite
    res = subprocess.run(
        [sys.executable, str(runner_path), "--integration"],
        cwd=str(root_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "Python Integration Tests" in res.stdout
    assert "PASSED" in res.stdout
    assert "ALL TEST SUITES PASSED" in res.stdout
