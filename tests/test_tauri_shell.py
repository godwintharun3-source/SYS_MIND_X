"""Unit and contract tests for the Tauri desktop presentation shell and safe window configuration."""

import json
from pathlib import Path
import subprocess
import pytest
from system_mind.packaging import (
    TauriShellAuditResult,
    TauriShellValidator,
)


def test_audit_shell_success() -> None:
    """Verifies that the canonical apps/desktop/src-tauri shell passes all security and window invariants."""
    result = TauriShellValidator.audit_shell()

    assert isinstance(result, TauriShellAuditResult)
    assert result.is_valid is True
    assert result.product_name == "SYSTEM MIND X"
    assert result.identifier == "org.systemmind.desktop"
    assert result.version == "1.0.0"
    assert result.windows_count == 1
    assert result.csp_enforced is True
    assert result.ambient_shell_disabled is True
    assert result.fullscreen_blocked is True
    assert len(result.verified_files) == len(TauriShellValidator.REQUIRED_FILES)
    assert len(result.missing_files) == 0
    assert len(result.issues) == 0


def test_audit_shell_missing_directory(tmp_path: Path) -> None:
    """Verifies that missing src-tauri directory is handled gracefully with an error report."""
    result = TauriShellValidator.audit_shell(root_dir=tmp_path)

    assert result.is_valid is False
    assert len(result.missing_files) == len(TauriShellValidator.REQUIRED_FILES)
    assert any("Tauri desktop shell directory missing" in issue for issue in result.issues)


def test_audit_shell_missing_file(tmp_path: Path) -> None:
    """Verifies that missing required files are flagged in the audit result."""
    src_tauri = tmp_path / "apps" / "desktop" / "src-tauri"
    src_tauri.mkdir(parents=True)

    # Populate only Cargo.toml
    cargo_path = src_tauri / "Cargo.toml"
    cargo_path.write_text(
        """
        [package]
        name = "system-mind-desktop"
        version = "1.0.0"
        edition = "2021"
        """,
        encoding="utf-8",
    )

    result = TauriShellValidator.audit_shell(root_dir=tmp_path)
    assert result.is_valid is False
    assert "tauri.conf.json" in result.missing_files
    assert "capabilities/default.json" in result.missing_files
    assert any("tauri.conf.json" in issue for issue in result.issues)


def test_audit_shell_fullscreen_violation(tmp_path: Path) -> None:
    """Verifies that enabling fullscreen by default triggers a hard safety constraint violation."""
    src_tauri = tmp_path / "apps" / "desktop" / "src-tauri"
    caps = src_tauri / "capabilities"
    src_dir = src_tauri / "src"
    caps.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    # Cargo.toml
    (src_tauri / "Cargo.toml").write_text(
        '[package]\nname = "system-mind-desktop"\nversion = "1.0.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    (src_dir / "main.rs").write_text("fn main() {}", encoding="utf-8")
    (src_dir / "lib.rs").write_text("pub fn run() {}", encoding="utf-8")
    (caps / "default.json").write_text('{"permissions": ["core:default"]}', encoding="utf-8")

    # tauri.conf.json with fullscreen: true (ILLEGAL)
    (src_tauri / "tauri.conf.json").write_text(
        json.dumps(
            {
                "productName": "SYSTEM MIND X",
                "identifier": "org.systemmind.desktop",
                "version": "1.0.0",
                "app": {
                    "windows": [
                        {
                            "title": "SYSTEM MIND X",
                            "width": 1280,
                            "height": 860,
                            "minWidth": 960,
                            "minHeight": 640,
                            "resizable": True,
                            "fullscreen": True,  # Violation!
                            "decorations": True,
                        }
                    ],
                    "security": {
                        "csp": "default-src 'self';"
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = TauriShellValidator.audit_shell(root_dir=tmp_path)
    assert result.is_valid is False
    assert result.fullscreen_blocked is False
    assert any("Main window must NOT be fullscreen by default" in issue for issue in result.issues)


def test_audit_shell_weak_csp_violation(tmp_path: Path) -> None:
    """Verifies that weak or wildcard CSP policies are flagged as security violations."""
    src_tauri = tmp_path / "apps" / "desktop" / "src-tauri"
    caps = src_tauri / "capabilities"
    src_dir = src_tauri / "src"
    caps.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    (src_tauri / "Cargo.toml").write_text(
        '[package]\nname = "system-mind-desktop"\nversion = "1.0.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    (src_dir / "main.rs").write_text("fn main() {}", encoding="utf-8")
    (src_dir / "lib.rs").write_text("pub fn run() {}", encoding="utf-8")
    (caps / "default.json").write_text('{"permissions": ["core:default"]}', encoding="utf-8")

    # Weak CSP with script-src * and unsafe-eval
    (src_tauri / "tauri.conf.json").write_text(
        json.dumps(
            {
                "productName": "SYSTEM MIND X",
                "identifier": "org.systemmind.desktop",
                "version": "1.0.0",
                "app": {
                    "windows": [
                        {
                            "title": "SYSTEM MIND X",
                            "width": 1280,
                            "height": 860,
                            "minWidth": 960,
                            "minHeight": 640,
                            "resizable": True,
                            "fullscreen": False,
                            "decorations": True,
                        }
                    ],
                    "security": {
                        "csp": "script-src * 'unsafe-eval';"  # Missing default-src 'self' & has unsafe-eval
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = TauriShellValidator.audit_shell(root_dir=tmp_path)
    assert result.is_valid is False
    assert result.csp_enforced is False
    assert any("Content Security Policy must enforce" in issue for issue in result.issues)
    assert any("unsafe script execution directives" in issue for issue in result.issues)


def test_audit_shell_prohibited_capability(tmp_path: Path) -> None:
    """Verifies that granting ambient shell execution capability is caught by the audit."""
    src_tauri = tmp_path / "apps" / "desktop" / "src-tauri"
    caps = src_tauri / "capabilities"
    src_dir = src_tauri / "src"
    caps.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    (src_tauri / "Cargo.toml").write_text(
        '[package]\nname = "system-mind-desktop"\nversion = "1.0.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    (src_dir / "main.rs").write_text("fn main() {}", encoding="utf-8")
    (src_dir / "lib.rs").write_text("pub fn run() {}", encoding="utf-8")

    # Illegally granting shell:allow-execute
    (caps / "default.json").write_text(
        json.dumps({"permissions": ["core:default", "shell:allow-execute"]}),
        encoding="utf-8",
    )

    (src_tauri / "tauri.conf.json").write_text(
        json.dumps(
            {
                "productName": "SYSTEM MIND X",
                "identifier": "org.systemmind.desktop",
                "version": "1.0.0",
                "app": {
                    "windows": [
                        {
                            "title": "SYSTEM MIND X",
                            "width": 1280,
                            "height": 860,
                            "minWidth": 960,
                            "minHeight": 640,
                            "resizable": True,
                            "fullscreen": False,
                            "decorations": True,
                        }
                    ],
                    "security": {
                        "csp": "default-src 'self';"
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = TauriShellValidator.audit_shell(root_dir=tmp_path)
    assert result.is_valid is False
    assert result.ambient_shell_disabled is False
    assert any("prohibited capability permission 'shell:allow-execute'" in issue for issue in result.issues)


def test_audit_shell_window_geometry_underflow(tmp_path: Path) -> None:
    """Verifies that window geometry underflowing minimum safety constraints is rejected."""
    src_tauri = tmp_path / "apps" / "desktop" / "src-tauri"
    caps = src_tauri / "capabilities"
    src_dir = src_tauri / "src"
    caps.mkdir(parents=True)
    src_dir.mkdir(parents=True)

    (src_tauri / "Cargo.toml").write_text(
        '[package]\nname = "system-mind-desktop"\nversion = "1.0.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    (src_dir / "main.rs").write_text("fn main() {}", encoding="utf-8")
    (src_dir / "lib.rs").write_text("pub fn run() {}", encoding="utf-8")
    (caps / "default.json").write_text('{"permissions": ["core:default"]}', encoding="utf-8")

    # Window with dimensions below required minimums
    (src_tauri / "tauri.conf.json").write_text(
        json.dumps(
            {
                "productName": "SYSTEM MIND X",
                "identifier": "org.systemmind.desktop",
                "version": "1.0.0",
                "app": {
                    "windows": [
                        {
                            "title": "Tiny Window",
                            "width": 500,  # Below 800
                            "height": 400,  # Below 600
                            "minWidth": 300,  # Below 640
                            "minHeight": 200,  # Below 480
                            "resizable": True,
                            "fullscreen": False,
                            "decorations": True,
                        }
                    ],
                    "security": {
                        "csp": "default-src 'self';"
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    result = TauriShellValidator.audit_shell(root_dir=tmp_path)
    assert result.is_valid is False
    assert any("Main window width (500) must be at least 800" in issue for issue in result.issues)
    assert any("Main window height (400) must be at least 600" in issue for issue in result.issues)
    assert any("Main window minWidth (300) must be at least 640" in issue for issue in result.issues)
    assert any("Main window minHeight (200) must be at least 480" in issue for issue in result.issues)


def test_native_desktop_shell_cargo_test() -> None:
    """Verifies that native unit tests within the desktop shell crate compile and pass."""
    proc = subprocess.run(
        ["cargo", "test", "--manifest-path", "apps/desktop/src-tauri/Cargo.toml"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"cargo test failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}"
    assert "test tests::test_shell_security_invariants ... ok" in proc.stdout
    assert "test tests::test_window_geometry_invariants ... ok" in proc.stdout


def test_packaging_module_exports() -> None:
    """Verifies that TauriShellValidator and TauriShellAuditResult are exported from packaging."""
    from system_mind.packaging import TauriShellValidator as TSV
    from system_mind.packaging import TauriShellAuditResult as TSAR

    assert TSV is not None
    assert TSAR is not None
