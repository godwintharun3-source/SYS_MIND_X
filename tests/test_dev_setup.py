"""Unit, integration, and contract tests for local development scripts and setup instructions."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT_DIR / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from dev_setup import PrerequisiteChecker, WorkspaceCleaner
from system_mind.packaging.dev_setup import DevSetupValidator


@pytest.mark.unit
def test_prerequisite_checker_python_satisfied() -> None:
    """Verifies that Python toolchain check correctly detects active interpreter and version."""
    py_info = PrerequisiteChecker.check_python()
    assert py_info["tool"] == "python"
    assert py_info["installed"] is True
    assert py_info["satisfied"] is True
    assert py_info["min_version"] == "3.10.0"
    assert py_info["executable"] == sys.executable


@pytest.mark.unit
def test_prerequisite_checker_tools_detection() -> None:
    """Verifies toolchain checkers for git, cargo, node, and npm."""
    git_info = PrerequisiteChecker.check_git()
    assert git_info["tool"] == "git"
    assert git_info["installed"] is True

    cargo_info = PrerequisiteChecker.check_rust()
    assert cargo_info["tool"] == "cargo"
    assert cargo_info["min_version"] == "1.75.0"

    node_info = PrerequisiteChecker.check_node()
    assert node_info["tool"] == "node"
    assert node_info["min_version"] == "18.0.0"

    npm_info = PrerequisiteChecker.check_npm()
    assert npm_info["tool"] == "npm"
    assert npm_info["min_version"] == "9.0.0"


@pytest.mark.unit
def test_prerequisite_checker_check_all() -> None:
    """Verifies that check_all returns comprehensive structured diagnostics."""
    diag = PrerequisiteChecker.check_all()
    assert "all_satisfied" in diag
    assert "tools" in diag
    assert len(diag["tools"]) == 5
    assert "config" in diag
    assert "database" in diag
    assert diag["config"]["env_example_present"] is True


@pytest.mark.unit
def test_workspace_cleaner_bounded_traversal() -> None:
    """Verifies that WorkspaceCleaner preview never escapes ROOT_DIR."""
    preview = WorkspaceCleaner.clean(dry_run=True)
    assert isinstance(preview, list)
    for path_str in preview:
        resolved = (ROOT_DIR / path_str).resolve()
        assert ROOT_DIR in resolved.parents or resolved == ROOT_DIR


@pytest.mark.integration
def test_workspace_cleaner_actual_clean_on_mock_artifacts() -> None:
    """Verifies that WorkspaceCleaner removes targeted build directories without touching code."""
    # Create a mock build artifact inside target/mock_test_dir
    mock_dir = ROOT_DIR / "target" / "mock_test_dir"
    mock_dir.mkdir(parents=True, exist_ok=True)
    test_file = mock_dir / "dummy.txt"
    test_file.write_text("temporary artifact", encoding="utf-8")

    assert test_file.exists()

    # Clean without clean_all (target is in TARGET_DIRS)
    removed = WorkspaceCleaner.clean(dry_run=False, clean_all=False)
    assert any("target" in r for r in removed)
    assert not test_file.exists()


@pytest.mark.integration
def test_dev_setup_cli_check_command() -> None:
    """Verifies execution of 'python3 tools/dev_setup.py check' with --json."""
    cli_path = TOOLS_DIR / "dev_setup.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--json", "check"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert "all_satisfied" in data
    assert len(data["tools"]) == 5


@pytest.mark.integration
def test_dev_setup_cli_bootstrap_dry_run() -> None:
    """Verifies execution of 'python3 tools/dev_setup.py bootstrap --dry-run'."""
    cli_path = TOOLS_DIR / "dev_setup.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "bootstrap", "--dry-run"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    output = proc.stdout
    assert "Step 1: Toolchain prerequisites verified" in output
    assert "Step 2:" in output
    assert "Step 3:" in output
    assert "BOOTSTRAP COMPLETE" in output


@pytest.mark.integration
def test_dev_setup_cli_clean_dry_run() -> None:
    """Verifies execution of 'python3 tools/dev_setup.py clean --dry-run' with --json."""
    cli_path = TOOLS_DIR / "dev_setup.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--json", "clean", "--dry-run"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["dry_run"] is True
    assert isinstance(data["removed"], list)


@pytest.mark.integration
def test_setup_dev_sh_script_execution() -> None:
    """Verifies execution and unprivileged safety of tools/setup_dev.sh."""
    sh_path = TOOLS_DIR / "setup_dev.sh"
    assert sh_path.exists()

    content = sh_path.read_text(encoding="utf-8")
    executable_lines = [
        line.strip()
        for line in content.splitlines()
        if not line.strip().startswith("#") and not line.strip().startswith("echo")
    ]
    assert not any(line.startswith("sudo ") for line in executable_lines)
    assert "id -u" in content  # root execution guard

    proc = subprocess.run(
        [str(sh_path), "check"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    assert "SYSTEM MIND X — Developer Environment Diagnostics" in proc.stdout


@pytest.mark.unit
def test_setup_dev_ps1_script_content() -> None:
    """Verifies PowerShell wrapper tools/setup_dev.ps1 exists and follows safety rules."""
    ps1_path = TOOLS_DIR / "setup_dev.ps1"
    assert ps1_path.exists()

    content = ps1_path.read_text(encoding="utf-8")
    assert "dev_setup.py" in content
    assert "Administrator" in content  # admin warning guard


@pytest.mark.contract
def test_dev_setup_validator_clean_audit() -> None:
    """Verifies that DevSetupValidator passes audit with zero issues."""
    result = DevSetupValidator.audit(ROOT_DIR)
    assert result.valid is True
    assert result.required_files_present is True
    assert result.prerequisites_valid is True
    assert result.cleaner_bounded is True
    assert len(result.issues) == 0


@pytest.mark.contract
def test_development_setup_documentation_completeness() -> None:
    """Verifies that docs/DEVELOPMENT_SETUP.md contains all mandatory setup sections."""
    doc_path = ROOT_DIR / "docs" / "DEVELOPMENT_SETUP.md"
    assert doc_path.exists()

    content = doc_path.read_text(encoding="utf-8")
    mandatory_sections = [
        "Supported Development Platforms",
        "Prerequisites & Toolchain Requirements",
        "Quickstart (Automated Bootstrap)",
        "Manual Step-by-Step Setup",
        "Daily Development Tooling",
        "Monorepo Boundary Rules",
        "Troubleshooting",
    ]
    for section in mandatory_sections:
        assert section in content, f"Missing section '{section}' in docs/DEVELOPMENT_SETUP.md"
