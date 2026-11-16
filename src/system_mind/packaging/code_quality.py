"""Validator for multi-language formatting, linting configurations, and static analysis gates."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None


@dataclass(frozen=True)
class CodeQualityAuditResult:
    """Audit outcome for multi-language code quality configurations and linter policies."""

    is_valid: bool
    verified_configs: List[str]
    missing_configs: List[str]
    python_tools_configured: List[str]
    rust_configured: bool
    typescript_configured: bool
    pre_commit_configured: bool
    issues: List[str] = field(default_factory=list)


class CodeQualityValidator:
    """Enforces presence and security correctness of formatting, linting, and AST safety configs."""

    REQUIRED_CONFIG_FILES = [
        ".flake8",
        ".pre-commit-config.yaml",
        "rustfmt.toml",
        "clippy.toml",
        "apps/desktop/.eslintrc.json",
        "apps/desktop/.prettierrc.json",
    ]

    REQUIRED_PYPROJECT_TOOLS = ["black", "mypy", "ruff"]

    @classmethod
    def audit_quality_configs(cls, root_dir: Optional[Path] = None) -> CodeQualityAuditResult:
        """Executes an audit verifying that all formatting, linting, and safety configs are valid."""
        root = root_dir or Path.cwd()
        issues: List[str] = []
        verified: List[str] = []
        missing: List[str] = []

        # 1. Verify required configuration files exist
        for rel_file in cls.REQUIRED_CONFIG_FILES:
            target = root / rel_file
            if target.exists() and target.is_file():
                verified.append(rel_file)
            else:
                missing.append(rel_file)
                issues.append(f"Required quality configuration file missing: '{rel_file}'")

        # 2. Inspect pyproject.toml tool tables
        pyproject_path = root / "pyproject.toml"
        found_py_tools: List[str] = []
        if pyproject_path.exists():
            try:
                with open(pyproject_path, "rb") as f:
                    pyproj_data = tomllib.load(f)
                tool_tables = pyproj_data.get("tool", {})
                for expected_tool in cls.REQUIRED_PYPROJECT_TOOLS:
                    if expected_tool in tool_tables:
                        found_py_tools.append(expected_tool)
                    else:
                        issues.append(f"pyproject.toml missing required tool configuration: '[tool.{expected_tool}]'")
            except Exception as e:
                issues.append(f"Failed to parse pyproject.toml: {e}")
        else:
            issues.append("pyproject.toml not found")

        # 3. Inspect apps/desktop/.eslintrc.json
        eslint_path = root / "apps" / "desktop" / ".eslintrc.json"
        ts_configured = False
        if eslint_path.exists():
            try:
                with open(eslint_path, "r", encoding="utf-8") as f:
                    eslint_data = json.load(f)
                rules = eslint_data.get("rules", {})
                if rules.get("no-eval") != "error":
                    issues.append(".eslintrc.json must set 'no-eval': 'error'")
                if "no-restricted-imports" not in rules:
                    issues.append(".eslintrc.json must restrict ambient execution imports (child_process, execa)")
                ts_configured = True
            except Exception as e:
                issues.append(f"Failed to parse .eslintrc.json: {e}")

        # 4. Inspect rustfmt.toml and clippy.toml
        rust_configured = False
        rustfmt_path = root / "rustfmt.toml"
        clippy_path = root / "clippy.toml"
        if rustfmt_path.exists() and clippy_path.exists():
            rustfmt_content = rustfmt_path.read_text(encoding="utf-8")
            clippy_content = clippy_path.read_text(encoding="utf-8")
            if 'edition = "2021"' not in rustfmt_content:
                issues.append("rustfmt.toml must declare edition = \"2021\"")
            if "cognitive-complexity-threshold" not in clippy_content:
                issues.append("clippy.toml must declare cognitive-complexity-threshold")
            rust_configured = True

        # 5. Inspect .pre-commit-config.yaml
        precommit_configured = False
        precommit_path = root / ".pre-commit-config.yaml"
        if precommit_path.exists():
            if yaml is None:
                # Basic string fallback if yaml parser not available
                content = precommit_path.read_text(encoding="utf-8")
                if "ambient-shell" not in content:
                    issues.append(".pre-commit-config.yaml missing ambient-shell safety hook")
                precommit_configured = True
            else:
                try:
                    with open(precommit_path, "r", encoding="utf-8") as f:
                        pc_data = yaml.safe_load(f)
                    repos = pc_data.get("repos", []) if isinstance(pc_data, dict) else []
                    has_ast_hook = any(
                        any("ambient-shell" in hook.get("id", "") for hook in repo.get("hooks", []))
                        for repo in repos
                    )
                    if not has_ast_hook:
                        issues.append(".pre-commit-config.yaml missing ambient-shell safety hook")
                    precommit_configured = True
                except Exception as e:
                    issues.append(f"Failed to parse .pre-commit-config.yaml: {e}")

        is_valid = len(issues) == 0

        return CodeQualityAuditResult(
            is_valid=is_valid,
            verified_configs=verified,
            missing_configs=missing,
            python_tools_configured=found_py_tools,
            rust_configured=rust_configured,
            typescript_configured=ts_configured,
            pre_commit_configured=precommit_configured,
            issues=issues,
        )
