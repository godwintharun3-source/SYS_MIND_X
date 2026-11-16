"""Unit and contract tests for multi-language formatting, linting, and static analysis configurations."""

import ast
import json
from pathlib import Path
import subprocess
import pytest

from system_mind.packaging import (
    CodeQualityAuditResult,
    CodeQualityValidator,
)
from tools.lint import AstSafetyChecker, check_python_ast_safety


def test_code_quality_audit_success() -> None:
    """Verifies that the canonical repository formatting and linting configurations pass the quality audit."""
    result = CodeQualityValidator.audit_quality_configs()

    assert isinstance(result, CodeQualityAuditResult)
    assert result.is_valid is True
    assert len(result.verified_configs) == len(CodeQualityValidator.REQUIRED_CONFIG_FILES)
    assert len(result.missing_configs) == 0
    assert set(result.python_tools_configured) >= {"black", "mypy", "ruff"}
    assert result.rust_configured is True
    assert result.typescript_configured is True
    assert result.pre_commit_configured is True
    assert len(result.issues) == 0


def test_code_quality_audit_missing_config_file(tmp_path: Path) -> None:
    """Verifies that missing linter configuration files are reported as failures."""
    result = CodeQualityValidator.audit_quality_configs(root_dir=tmp_path)

    assert result.is_valid is False
    assert len(result.missing_configs) == len(CodeQualityValidator.REQUIRED_CONFIG_FILES)
    assert any("rustfmt.toml" in issue for issue in result.issues)
    assert any(".pre-commit-config.yaml" in issue for issue in result.issues)


def test_code_quality_audit_missing_pyproject_tool(tmp_path: Path) -> None:
    """Verifies that pyproject.toml lacking tool configuration tables is flagged."""
    # Write only pyproject.toml without tool tables
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\nversion = "1.0.0"\n', encoding="utf-8")

    result = CodeQualityValidator.audit_quality_configs(root_dir=tmp_path)
    assert result.is_valid is False
    assert any("pyproject.toml missing required tool configuration: '[tool.black]'" in issue for issue in result.issues)
    assert any("pyproject.toml missing required tool configuration: '[tool.ruff]'" in issue for issue in result.issues)


def test_code_quality_audit_insecure_eslint_rule(tmp_path: Path) -> None:
    """Verifies that an ESLint configuration lacking no-eval or ambient import bans fails the audit."""
    desktop_dir = tmp_path / "apps" / "desktop"
    desktop_dir.mkdir(parents=True)

    # Insecure eslint config (no-eval off, no restricted imports)
    (desktop_dir / ".eslintrc.json").write_text(
        json.dumps({
            "root": True,
            "rules": {
                "no-eval": "off"
            }
        }),
        encoding="utf-8",
    )

    result = CodeQualityValidator.audit_quality_configs(root_dir=tmp_path)
    assert result.is_valid is False
    assert any(".eslintrc.json must set 'no-eval': 'error'" in issue for issue in result.issues)
    assert any("must restrict ambient execution imports" in issue for issue in result.issues)


def test_code_quality_audit_missing_ambient_shell_hook(tmp_path: Path) -> None:
    """Verifies that .pre-commit-config.yaml without ambient shell safety hook is caught."""
    (tmp_path / ".pre-commit-config.yaml").write_text(
        """
        repos:
          - repo: https://github.com/psf/black
            hooks:
              - id: black
        """,
        encoding="utf-8",
    )

    result = CodeQualityValidator.audit_quality_configs(root_dir=tmp_path)
    assert result.is_valid is False
    assert any("missing ambient-shell safety hook" in issue for issue in result.issues)


def test_ast_safety_checker_catches_ambient_shell() -> None:
    """Verifies that AstSafetyChecker flags os.system and shell=True calls with line numbers."""
    unsafe_code = """
import os
import subprocess

def run_untrusted():
    os.system("rm -rf /")
    subprocess.call(["ls", "-la"], shell=True)
    subprocess.run("cat /etc/passwd", shell=True)
"""
    tree = ast.parse(unsafe_code, filename="unsafe_sample.py")
    checker = AstSafetyChecker("unsafe_sample.py")
    checker.visit(tree)

    assert len(checker.violations) == 3
    assert any("os.system" in v and "unsafe_sample.py:6" in v for v in checker.violations)
    assert any("shell=True" in v and "unsafe_sample.py:7" in v for v in checker.violations)
    assert any("shell=True" in v and "unsafe_sample.py:8" in v for v in checker.violations)


def test_ast_safety_checker_clean_code() -> None:
    """Verifies that compliant code without ambient shell execution passes without violations."""
    clean_code = """
import subprocess

def run_safe():
    # Compliant: explicit arg list, no shell=True
    subprocess.run(["python3", "--version"], check=True)
"""
    tree = ast.parse(clean_code, filename="clean_sample.py")
    checker = AstSafetyChecker("clean_sample.py")
    checker.visit(tree)

    assert len(checker.violations) == 0


def test_tools_lint_cli_execution() -> None:
    """Verifies that tools/lint.py executes cleanly across all monorepo tiers with exit code 0."""
    proc = subprocess.run(
        ["python3", "tools/lint.py", "--all"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"tools/lint.py failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "Python syntax verification clean" in proc.stdout
    assert "Zero ambient shell violations detected" in proc.stdout
    assert "TypeScript presentation layer safety verified" in proc.stdout
    assert "Rust static analysis clean" in proc.stdout


def test_packaging_module_exports_quality_validator() -> None:
    """Verifies that CodeQualityValidator and CodeQualityAuditResult are exported from packaging."""
    from system_mind.packaging import CodeQualityValidator as CQV
    from system_mind.packaging import CodeQualityAuditResult as CQAR

    assert CQV is not None
    assert CQAR is not None
