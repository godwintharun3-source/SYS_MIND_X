"""Unit and contract tests for SYSTEM MIND X Python backend packaging and dependency configuration."""

import io
from pathlib import Path
import pytest
from system_mind import __version__
from system_mind.cli import main
from system_mind.packaging.models import PackageMetadata, PackageVerificationResult
from system_mind.packaging.validator import PackageConfigValidator


def test_pyproject_toml_exists_and_loads():
    """Verify pyproject.toml exists and can be parsed via standard tomllib."""
    data = PackageConfigValidator.load_pyproject()
    assert "project" in data
    assert data["project"]["name"] == "system-mind-backend"
    assert data["project"]["version"] == "1.0.0"
    assert data["project"]["requires-python"] == ">=3.10"


def test_package_config_validator_passes():
    """Verify that current repository configuration passes all packaging audits cleanly."""
    result = PackageConfigValidator.validate()
    assert result.is_valid is True
    assert result.name == "system-mind-backend"
    assert result.version == __version__
    assert result.requires_python == ">=3.10"
    assert result.entrypoint_valid is True
    assert len(result.unpinned_dependencies) == 0
    assert len(result.prohibited_dependencies) == 0
    assert len(result.issues) == 0


def test_validator_detects_unpinned_dependency(tmp_path):
    """Verify validator flags any floating or unpinned dependencies."""
    mock_toml = """
[project]
name = "system-mind-backend"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "requests>=2.28.0",
]

[project.scripts]
system-mind = "system_mind.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    p = tmp_path / "pyproject.toml"
    p.write_text(mock_toml, encoding="utf-8")

    res = PackageConfigValidator.validate(p)
    assert res.is_valid is False
    assert "requests>=2.28.0" in res.unpinned_dependencies
    assert any("Unpinned dependency detected" in issue for issue in res.issues)


def test_validator_detects_prohibited_ambient_package(tmp_path):
    """Verify validator flags banned ambient execution packages."""
    mock_toml = """
[project]
name = "system-mind-backend"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "sh==1.14.3",
]

[project.scripts]
system-mind = "system_mind.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    p = tmp_path / "pyproject.toml"
    p.write_text(mock_toml, encoding="utf-8")

    res = PackageConfigValidator.validate(p)
    assert res.is_valid is False
    assert "sh" in res.prohibited_dependencies
    assert any("Prohibited package detected" in issue for issue in res.issues)


def test_validator_detects_version_desynchronization(tmp_path):
    """Verify validator flags mismatch between pyproject.toml and package __version__."""
    mock_toml = """
[project]
name = "system-mind-backend"
version = "0.9.0"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
system-mind = "system_mind.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    p = tmp_path / "pyproject.toml"
    p.write_text(mock_toml, encoding="utf-8")

    res = PackageConfigValidator.validate(p)
    assert res.is_valid is False
    assert any("Version desynchronization" in issue for issue in res.issues)


def test_validator_detects_invalid_cli_entrypoint(tmp_path):
    """Verify validator flags invalid or missing CLI script entrypoint."""
    mock_toml = """
[project]
name = "system-mind-backend"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = []

[project.scripts]
wrong-tool = "some.module:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""
    p = tmp_path / "pyproject.toml"
    p.write_text(mock_toml, encoding="utf-8")

    res = PackageConfigValidator.validate(p)
    assert res.is_valid is False
    assert res.entrypoint_valid is False
    assert any("Missing or invalid CLI entrypoint" in issue for issue in res.issues)


def test_cli_main_status_command(capsys):
    """Verify system-mind CLI --status command output."""
    ret = main(["--status"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "SYSTEM MIND X Control Plane v1.0.0" in captured.out
    assert "Temporal Digital Twin: Ready" in captured.out
    assert "Intelligence Engines: 14/14 Registered" in captured.out


def test_cli_main_audit_baseline_command(capsys):
    """Verify system-mind CLI --audit-baseline command output."""
    ret = main(["--audit-baseline"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Auditing Architecture Baseline v1.0..." in captured.out
    assert "Status: FROZEN_APPROVED" in captured.out
    assert "Verified Subsystems: 14/14" in captured.out


def test_cli_main_verify_boundaries_command(capsys):
    """Verify system-mind CLI --verify-boundaries command output."""
    ret = main(["--verify-boundaries"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Verifying Monorepo Top-Level Boundaries..." in captured.out
    assert "Status: VALID" in captured.out


def test_requirements_files_exist_and_pinned():
    """Verify requirements.txt and requirements-dev.txt presence and pinning."""
    req_prod = Path("requirements.txt")
    assert req_prod.exists()
    assert req_prod.is_file()

    req_dev = Path("requirements-dev.txt")
    assert req_dev.exists()
    assert req_dev.is_file()

    lines = [
        line.strip()
        for line in req_dev.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert len(lines) >= 4
    for line in lines:
        assert "==" in line, f"Development dependency '{line}' must be pinned with '=='."
