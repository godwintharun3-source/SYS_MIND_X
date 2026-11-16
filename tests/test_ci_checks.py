"""Unit, integration, and contract tests for CI workflows, dependency reviews, and local CI runner."""

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

from system_mind.packaging.ci_checks import CiChecksValidator
from system_mind.packaging.dependency_review import DependencyReviewer


@pytest.mark.unit
def test_ci_workflow_yaml_syntax_and_jobs() -> None:
    """Verifies that .github/workflows/ci.yml exists and contains all required polyglot jobs."""
    ci_file = ROOT_DIR / ".github" / "workflows" / "ci.yml"
    assert ci_file.exists()

    content = ci_file.read_text(encoding="utf-8")
    assert "name: SYSTEM MIND X CI" in content
    assert "branches: [main, develop]" in content

    required_jobs = [
        "lint-and-safety",
        "test-python",
        "test-rust",
        "test-frontend",
        "database-migrations",
    ]
    for job in required_jobs:
        assert f"{job}:" in content, f"Missing job '{job}' in ci.yml"


@pytest.mark.unit
def test_dependency_review_workflow_yaml_syntax() -> None:
    """Verifies that .github/workflows/dependency-review.yml exists and defines dependency auditing."""
    wf_file = ROOT_DIR / ".github" / "workflows" / "dependency-review.yml"
    assert wf_file.exists()

    content = wf_file.read_text(encoding="utf-8")
    assert "name: Dependency Review & Supply Chain Audit" in content
    assert "dependency-audit:" in content
    assert "tools/ci_runner.py deps" in content


@pytest.mark.contract
def test_dependency_reviewer_audit_clean_repository() -> None:
    """Verifies that DependencyReviewer passes on repository manifests with zero issues."""
    result = DependencyReviewer.audit(ROOT_DIR)
    assert result.valid is True
    assert result.python_packages_count > 0
    assert result.node_packages_count > 0
    assert len(result.issues) == 0


@pytest.mark.unit
def test_dependency_reviewer_detects_unpinned_python_dependency() -> None:
    """Verifies that unpinned Python dependencies are rejected."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "requirements.txt").write_text("requests>=2.28.0\n", encoding="utf-8")
        (tmp_path / "requirements-dev.txt").write_text("# dev deps\n", encoding="utf-8")

        result = DependencyReviewer.audit(tmp_path)
        assert result.valid is False
        assert any("Unpinned dependency" in issue for issue in result.issues)


@pytest.mark.unit
def test_dependency_reviewer_detects_banned_python_package() -> None:
    """Verifies that banned ambient shell execution Python packages are flagged."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "requirements.txt").write_text("sh==1.14.3\n", encoding="utf-8")
        (tmp_path / "requirements-dev.txt").write_text("# dev deps\n", encoding="utf-8")

        result = DependencyReviewer.audit(tmp_path)
        assert result.valid is False
        assert any("Banned ambient execution package 'sh'" in issue for issue in result.issues)


@pytest.mark.unit
def test_dependency_reviewer_detects_banned_node_package() -> None:
    """Verifies that banned ambient execution Node packages in apps/desktop/package.json are flagged."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        desktop_dir = tmp_path / "apps" / "desktop"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        pkg_json = {
            "name": "mock-desktop",
            "dependencies": {
                "react": "^18.3.1",
                "child_process": "^1.0.2",
            },
        }
        (desktop_dir / "package.json").write_text(json.dumps(pkg_json), encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("# clean\n", encoding="utf-8")
        (tmp_path / "requirements-dev.txt").write_text("# clean\n", encoding="utf-8")

        result = DependencyReviewer.audit(tmp_path)
        assert result.valid is False
        assert any("Banned ambient shell package 'child_process'" in issue for issue in result.issues)


@pytest.mark.unit
def test_dependency_reviewer_detects_banned_rust_crate() -> None:
    """Verifies that banned native binding crates (e.g. pyo3) in Cargo manifests are flagged."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        cargo_content = """
        [package]
        name = "mock-crate"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        pyo3 = "0.20"
        """
        (tmp_path / "Cargo.toml").write_text(cargo_content, encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("# clean\n", encoding="utf-8")
        (tmp_path / "requirements-dev.txt").write_text("# clean\n", encoding="utf-8")

        result = DependencyReviewer.audit(tmp_path)
        assert result.valid is False
        assert any("Forbidden native binding crate 'pyo3'" in issue for issue in result.issues)


@pytest.mark.contract
def test_ci_checks_validator_audits_clean() -> None:
    """Verifies that CiChecksValidator passes with zero issues on repository state."""
    result = CiChecksValidator.audit(ROOT_DIR)
    assert result.valid is True
    assert result.workflows_valid is True
    assert result.dependencies_valid is True
    assert result.ci_runner_valid is True
    assert len(result.issues) == 0


@pytest.mark.integration
def test_ci_runner_cli_dry_run() -> None:
    """Verifies execution of 'python3 tools/ci_runner.py all --dry-run'."""
    cli_path = TOOLS_DIR / "ci_runner.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--dry-run", "--json", "all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["all_passed"] is True
    assert len(data["stages"]) == 5
    stage_names = [s["stage"] for s in data["stages"]]
    assert "dependency-review" in stage_names
    assert "lint-and-ast-safety" in stage_names
    assert "schemas-parity-check" in stage_names
    assert "database-migrations" in stage_names
    assert "polyglot-tests" in stage_names


@pytest.mark.integration
def test_ci_runner_cli_deps_command() -> None:
    """Verifies execution of 'python3 tools/ci_runner.py deps --json'."""
    cli_path = TOOLS_DIR / "ci_runner.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--json", "deps"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["status"] == "PASSED"
    assert data["exit_code"] == 0
    assert len(data["issues"]) == 0


@pytest.mark.integration
def test_ci_runner_cli_lint_command_dry_run() -> None:
    """Verifies execution of 'python3 tools/ci_runner.py lint --dry-run --json'."""
    cli_path = TOOLS_DIR / "ci_runner.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--dry-run", "--json", "lint"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["all_passed"] is True
    assert len(data["stages"]) == 2


@pytest.mark.integration
def test_ci_runner_cli_test_command_dry_run() -> None:
    """Verifies execution of 'python3 tools/ci_runner.py test --dry-run --json'."""
    cli_path = TOOLS_DIR / "ci_runner.py"
    proc = subprocess.run(
        [sys.executable, str(cli_path), "--dry-run", "--json", "test"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    data = json.loads(proc.stdout)
    assert data["all_passed"] is True
    assert len(data["stages"]) == 1
