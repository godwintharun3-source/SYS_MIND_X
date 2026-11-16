"""Unit and contract tests for SYSTEM MIND X Rust system-agent workspace and crate boundaries."""

from pathlib import Path
import subprocess
import tomllib
import pytest
from system_mind.packaging.rust_workspace import (
    CrateBoundarySpec,
    RustWorkspaceAuditResult,
    RustWorkspaceValidator,
)


def test_root_cargo_toml_exists_and_loads():
    """Verify root Cargo.toml manifest defines the multi-crate workspace."""
    manifest = RustWorkspaceValidator.load_root_cargo_toml()
    assert "workspace" in manifest
    workspace = manifest["workspace"]
    assert workspace["resolver"] == "2"

    members = workspace.get("members", [])
    assert "crates/system-mind-common" in members
    assert "crates/system-mind-sensors" in members
    assert "crates/system-mind-broker" in members


def test_rust_workspace_audit_passes():
    """Verify that current repository Cargo workspace satisfies all crate boundary rules."""
    audit = RustWorkspaceValidator.audit_workspace()
    assert audit.is_valid is True
    assert audit.workspace_members_count == 3
    assert len(audit.verified_crates) == 3
    assert set(audit.verified_crates) == {
        "system-mind-common",
        "system-mind-sensors",
        "system-mind-broker",
    }
    assert len(audit.missing_crates) == 0
    assert len(audit.prohibited_dependencies) == 0
    assert len(audit.issues) == 0


def test_audit_detects_missing_crate_directory(tmp_path):
    """Verify validator flags missing crate directories."""
    mock_cargo = """
[workspace]
resolver = "2"
members = ["crates/system-mind-common", "crates/system-mind-sensors", "crates/system-mind-broker"]
"""
    (tmp_path / "Cargo.toml").write_text(mock_cargo, encoding="utf-8")
    (tmp_path / "crates").mkdir(parents=True)

    audit = RustWorkspaceValidator.audit_workspace(tmp_path)
    assert audit.is_valid is False
    assert len(audit.missing_crates) == 3
    assert any("Crate directory missing" in issue for issue in audit.issues)


def test_audit_detects_boundary_violation_prohibited_dep(tmp_path):
    """Verify validator flags illegal circular/backward crate dependencies."""
    mock_cargo = """
[workspace]
resolver = "2"
members = ["crates/system-mind-common", "crates/system-mind-sensors", "crates/system-mind-broker"]
"""
    (tmp_path / "Cargo.toml").write_text(mock_cargo, encoding="utf-8")

    # Create crates where common illegally depends on broker
    for name in ["system-mind-common", "system-mind-sensors", "system-mind-broker"]:
        c_dir = tmp_path / "crates" / name
        c_dir.mkdir(parents=True)
        if name == "system-mind-common":
            # Illegal dependency
            c_toml = f"""
[package]
name = "{name}"
version = "1.0.0"
edition = "2021"

[dependencies]
system-mind-broker = {{ path = "../system-mind-broker" }}
"""
        else:
            c_toml = f"""
[package]
name = "{name}"
version = "1.0.0"
edition = "2021"
"""
        (c_dir / "Cargo.toml").write_text(c_toml, encoding="utf-8")

    audit = RustWorkspaceValidator.audit_workspace(tmp_path)
    assert audit.is_valid is False
    assert any("system-mind-common -> system-mind-broker" in p for p in audit.prohibited_dependencies)
    assert any("Boundary violation" in issue for issue in audit.issues)


def test_cargo_test_workspace_execution():
    """Verify native Rust test suite passes across all workspace crates."""
    res = subprocess.run(
        ["cargo", "test", "--workspace"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "test result: ok" in res.stdout
