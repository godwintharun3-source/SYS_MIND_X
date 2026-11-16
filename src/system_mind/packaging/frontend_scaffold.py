"""Validator for the React and TypeScript desktop frontend scaffold and presentation boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class FrontendScaffoldAuditResult:
    """Audit outcome for desktop frontend scaffold, configuration, and wire types."""

    is_valid: bool
    package_name: str
    package_version: str
    verified_files: List[str]
    missing_files: List[str]
    prohibited_packages: List[str]
    wire_types_complete: bool
    issues: List[str] = field(default_factory=list)


class FrontendScaffoldValidator:
    """Enforces presentation layer sandbox boundaries, configuration validity, and wire type contracts."""

    DESKTOP_DIR = "apps/desktop"

    REQUIRED_FILES = [
        "package.json",
        "tsconfig.json",
        "tsconfig.node.json",
        "vite.config.ts",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/types/api.ts",
        "src/services/client.ts",
        "src/styles/index.css",
    ]

    PROHIBITED_PACKAGES = [
        "child_process",
        "execa",
        "shelljs",
        "sudo-prompt",
        "node-pty",
        "ffi-napi",
        "open",
        "node-powershell",
    ]

    REQUIRED_SCRIPTS = ["dev", "build", "test"]
    REQUIRED_CORE_DEPS = ["react", "react-dom"]

    REQUIRED_FILE_TRUST_STATES = [
        "QUARANTINED",
        "VERIFIED",
        "SANDBOXED",
        "BLOCKED",
        "ALLOWLISTED",
        "PROVENANCE_PENDING",
        "SECURITY_REVOKED",
        "STATIC_ANALYSIS_FAILED",
    ]

    REQUIRED_OWNERSHIP_STATES = [
        "SYSTEM_MANAGED",
        "VENDOR_MANAGED",
        "USER_MANAGED",
    ]

    @classmethod
    def load_json_file(cls, file_path: Path) -> Dict[str, Any]:
        """Loads and parses a JSON file."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def verify_wire_types(cls, types_file: Path) -> Tuple[bool, List[str]]:
        """Verifies that TypeScript wire definitions match architectural contracts."""
        if not types_file.exists():
            return False, [f"Types file missing at: {types_file}"]

        content = types_file.read_text(encoding="utf-8")
        issues: List[str] = []

        # Check ApiRequest and ApiResponse interfaces
        if "interface ApiRequest" not in content and "type ApiRequest" not in content:
            issues.append("Missing ApiRequest definition in api.ts")
        if "interface ApiResponse" not in content and "type ApiResponse" not in content:
            issues.append("Missing ApiResponse definition in api.ts")
        if "idempotency_key" not in content:
            issues.append("Missing idempotency_key in ApiRequest definition")

        # Check all 8 file trust lifecycle states
        for state in cls.REQUIRED_FILE_TRUST_STATES:
            if f'"{state}"' not in content:
                issues.append(f"Missing FileTrustState variant '{state}' in api.ts")

        # Check tripartite ownership states
        for ownership in cls.REQUIRED_OWNERSHIP_STATES:
            if f'"{ownership}"' not in content:
                issues.append(f"Missing ComponentOwnership variant '{ownership}' in api.ts")

        return len(issues) == 0, issues

    @classmethod
    def audit_scaffold(cls, root_dir: Optional[Path] = None) -> FrontendScaffoldAuditResult:
        """Executes a full compliance audit on the desktop frontend scaffold."""
        root = root_dir or Path.cwd()
        desktop_path = root / cls.DESKTOP_DIR
        issues: List[str] = []
        verified_files: List[str] = []
        missing_files: List[str] = []
        found_prohibited: List[str] = []
        pkg_name = ""
        pkg_version = ""

        if not desktop_path.exists() or not desktop_path.is_dir():
            return FrontendScaffoldAuditResult(
                is_valid=False,
                package_name="",
                package_version="",
                verified_files=[],
                missing_files=cls.REQUIRED_FILES,
                prohibited_packages=[],
                wire_types_complete=False,
                issues=[f"Desktop app directory missing at: {desktop_path}"],
            )

        # 1. Verify required files presence
        for rel_file in cls.REQUIRED_FILES:
            target = desktop_path / rel_file
            if target.exists() and target.is_file():
                verified_files.append(rel_file)
            else:
                missing_files.append(rel_file)
                issues.append(f"Required frontend scaffold file missing: '{rel_file}'")

        # 2. Inspect package.json
        pkg_json_path = desktop_path / "package.json"
        if pkg_json_path.exists():
            try:
                pkg_data = cls.load_json_file(pkg_json_path)
                pkg_name = pkg_data.get("name", "")
                pkg_version = pkg_data.get("version", "")

                if pkg_name != "@system-mind/desktop":
                    issues.append(
                        f"package.json name mismatch: expected '@system-mind/desktop', got '{pkg_name}'"
                    )

                if not re.match(r"^\d+\.\d+\.\d+", pkg_version):
                    issues.append(f"package.json invalid SemVer version: '{pkg_version}'")

                # Verify required scripts
                scripts = pkg_data.get("scripts", {})
                for script in cls.REQUIRED_SCRIPTS:
                    if script not in scripts:
                        issues.append(f"package.json missing required script: '{script}'")

                # Verify core dependencies
                deps = pkg_data.get("dependencies", {})
                dev_deps = pkg_data.get("devDependencies", {})
                all_deps = {**deps, **dev_deps}

                for req_dep in cls.REQUIRED_CORE_DEPS:
                    if req_dep not in deps:
                        issues.append(f"package.json missing required core dependency: '{req_dep}'")

                # Verify NO prohibited ambient execution packages
                for prohibited in cls.PROHIBITED_PACKAGES:
                    if prohibited in all_deps:
                        found_prohibited.append(prohibited)
                        issues.append(
                            f"Presentation boundary violation: prohibited package '{prohibited}' declared in dependencies"
                        )

            except Exception as e:
                issues.append(f"Failed to parse package.json: {e}")

        # 3. Inspect tsconfig.json
        tsconfig_path = desktop_path / "tsconfig.json"
        if tsconfig_path.exists():
            try:
                ts_data = cls.load_json_file(tsconfig_path)
                compiler_opts = ts_data.get("compilerOptions", {})
                if not compiler_opts.get("strict", False):
                    issues.append("tsconfig.json must enforce 'strict: true'")
            except Exception as e:
                issues.append(f"Failed to parse tsconfig.json: {e}")

        # 4. Verify TypeScript wire contracts
        types_path = desktop_path / "src" / "types" / "api.ts"
        wire_types_ok, wire_issues = cls.verify_wire_types(types_path)
        if not wire_types_ok:
            issues.extend(wire_issues)

        is_valid = len(issues) == 0

        return FrontendScaffoldAuditResult(
            is_valid=is_valid,
            package_name=pkg_name,
            package_version=pkg_version,
            verified_files=verified_files,
            missing_files=missing_files,
            prohibited_packages=found_prohibited,
            wire_types_complete=wire_types_ok,
            issues=issues,
        )
