"""Validator for the Tauri desktop presentation shell, safe window configuration, and CSP invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class TauriShellAuditResult:
    """Audit outcome for Tauri desktop shell configuration and safety invariants."""

    is_valid: bool
    product_name: str
    identifier: str
    version: str
    windows_count: int
    verified_files: List[str]
    missing_files: List[str]
    csp_enforced: bool
    ambient_shell_disabled: bool
    fullscreen_blocked: bool
    issues: List[str] = field(default_factory=list)


class TauriShellValidator:
    """Enforces desktop window safety, airtight CSP, and zero-ambient-shell invariants."""

    SRC_TAURI_DIR = "apps/desktop/src-tauri"

    REQUIRED_FILES = [
        "tauri.conf.json",
        "Cargo.toml",
        "src/main.rs",
        "src/lib.rs",
        "capabilities/default.json",
    ]

    PROHIBITED_PERMISSIONS = [
        "shell:allow-execute",
        "shell:allow-spawn",
        "shell:allow-open-program",
        "process:allow-restart",
        "process:allow-exit",
    ]

    @classmethod
    def load_json_file(cls, path: Path) -> Dict[str, Any]:
        """Loads and parses a JSON document."""
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def load_cargo_toml(cls, path: Path) -> Dict[str, Any]:
        """Loads and parses a Cargo.toml manifest."""
        if not path.exists():
            raise FileNotFoundError(f"Cargo.toml not found: {path}")
        with open(path, "rb") as f:
            return tomllib.load(f)

    @classmethod
    def audit_shell(cls, root_dir: Optional[Path] = None) -> TauriShellAuditResult:
        """Executes a full compliance audit on the Tauri desktop shell."""
        root = root_dir or Path.cwd()
        src_tauri_path = root / cls.SRC_TAURI_DIR
        issues: List[str] = []
        verified_files: List[str] = []
        missing_files: List[str] = []

        product_name = ""
        identifier = ""
        version = ""
        windows_count = 0
        csp_enforced = False
        ambient_shell_disabled = True
        fullscreen_blocked = False

        if not src_tauri_path.exists() or not src_tauri_path.is_dir():
            return TauriShellAuditResult(
                is_valid=False,
                product_name="",
                identifier="",
                version="",
                windows_count=0,
                verified_files=[],
                missing_files=cls.REQUIRED_FILES,
                csp_enforced=False,
                ambient_shell_disabled=True,
                fullscreen_blocked=False,
                issues=[f"Tauri desktop shell directory missing at: {src_tauri_path}"],
            )

        # 1. Verify required files
        for rel_file in cls.REQUIRED_FILES:
            target = src_tauri_path / rel_file
            if target.exists() and target.is_file():
                verified_files.append(rel_file)
            else:
                missing_files.append(rel_file)
                issues.append(f"Required Tauri shell file missing: '{rel_file}'")

        # 2. Inspect tauri.conf.json
        conf_path = src_tauri_path / "tauri.conf.json"
        if conf_path.exists():
            try:
                conf = cls.load_json_file(conf_path)
                product_name = conf.get("productName", "")
                identifier = conf.get("identifier", "")
                version = conf.get("version", "")

                if product_name != "SYSTEM MIND X":
                    issues.append(
                        f"tauri.conf.json productName mismatch: expected 'SYSTEM MIND X', got '{product_name}'"
                    )

                if not re.match(r"^[a-zA-Z0-9_\.]+\.[a-zA-Z0-9_]+$", identifier):
                    issues.append(
                        f"tauri.conf.json identifier must be reverse-domain: '{identifier}'"
                    )

                if not re.match(r"^\d+\.\d+\.\d+", version):
                    issues.append(
                        f"tauri.conf.json invalid SemVer version: '{version}'"
                    )

                # Windows validation
                app_cfg = conf.get("app", {})
                windows = app_cfg.get("windows", [])
                windows_count = len(windows)

                if windows_count == 0:
                    issues.append("tauri.conf.json must declare at least one window in 'app.windows'")
                else:
                    main_win = windows[0]
                    # Title
                    if not main_win.get("title"):
                        issues.append("Main window must specify a non-empty title")

                    # Geometry
                    width = main_win.get("width", 0)
                    height = main_win.get("height", 0)
                    min_width = main_win.get("minWidth", 0)
                    min_height = main_win.get("minHeight", 0)

                    if width < 800:
                        issues.append(f"Main window width ({width}) must be at least 800")
                    if height < 600:
                        issues.append(f"Main window height ({height}) must be at least 600")
                    if min_width < 640:
                        issues.append(f"Main window minWidth ({min_width}) must be at least 640")
                    if min_height < 480:
                        issues.append(f"Main window minHeight ({min_height}) must be at least 480")

                    if not main_win.get("resizable", False):
                        issues.append("Main window must be resizable")

                    # Mandatory non-fullscreen default
                    if main_win.get("fullscreen", False):
                        issues.append("Safety Invariant Violation: Main window must NOT be fullscreen by default")
                        fullscreen_blocked = False
                    else:
                        fullscreen_blocked = True

                    if not main_win.get("decorations", False):
                        issues.append("Main window must have window decorations enabled")

                # CSP validation
                sec_cfg = app_cfg.get("security", {})
                csp = sec_cfg.get("csp", "")

                if "default-src 'self'" in csp:
                    csp_enforced = True
                else:
                    issues.append("Content Security Policy must enforce \"default-src 'self'\"")

                if "script-src *" in csp or "unsafe-eval" in csp:
                    issues.append("Content Security Policy contains unsafe script execution directives")

            except Exception as e:
                issues.append(f"Failed to parse tauri.conf.json: {e}")

        # 3. Inspect capabilities/default.json
        cap_path = src_tauri_path / "capabilities" / "default.json"
        if cap_path.exists():
            try:
                cap_data = cls.load_json_file(cap_path)
                perms = cap_data.get("permissions", [])

                for prohibited in cls.PROHIBITED_PERMISSIONS:
                    if prohibited in perms:
                        ambient_shell_disabled = False
                        issues.append(
                            f"Presentation boundary violation: prohibited capability permission '{prohibited}' granted in default.json"
                        )

            except Exception as e:
                issues.append(f"Failed to parse capabilities/default.json: {e}")

        # 4. Inspect Cargo.toml
        cargo_path = src_tauri_path / "Cargo.toml"
        if cargo_path.exists():
            try:
                cargo_data = cls.load_cargo_toml(cargo_path)
                pkg = cargo_data.get("package", {})
                pkg_name = pkg.get("name", "")
                if pkg_name != "system-mind-desktop":
                    issues.append(
                        f"Cargo.toml package name mismatch: expected 'system-mind-desktop', got '{pkg_name}'"
                    )
            except Exception as e:
                issues.append(f"Failed to parse src-tauri/Cargo.toml: {e}")

        is_valid = len(issues) == 0

        return TauriShellAuditResult(
            is_valid=is_valid,
            product_name=product_name,
            identifier=identifier,
            version=version,
            windows_count=windows_count,
            verified_files=verified_files,
            missing_files=missing_files,
            csp_enforced=csp_enforced,
            ambient_shell_disabled=ambient_shell_disabled,
            fullscreen_blocked=fullscreen_blocked,
            issues=issues,
        )
