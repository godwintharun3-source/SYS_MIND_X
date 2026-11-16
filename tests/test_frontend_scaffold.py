"""Unit and contract tests for the React/TypeScript desktop frontend scaffold validator."""

import json
from pathlib import Path
import pytest
from system_mind.packaging import (
    FrontendScaffoldAuditResult,
    FrontendScaffoldValidator,
)


def test_audit_scaffold_success() -> None:
    """Verifies that the canonical apps/desktop repository scaffold passes all architectural invariants."""
    result = FrontendScaffoldValidator.audit_scaffold()

    assert isinstance(result, FrontendScaffoldAuditResult)
    assert result.is_valid is True
    assert result.package_name == "@system-mind/desktop"
    assert result.package_version == "1.0.0"
    assert len(result.verified_files) == len(FrontendScaffoldValidator.REQUIRED_FILES)
    assert len(result.missing_files) == 0
    assert len(result.prohibited_packages) == 0
    assert result.wire_types_complete is True
    assert len(result.issues) == 0


def test_audit_scaffold_missing_desktop_dir(tmp_path: Path) -> None:
    """Verifies that missing apps/desktop directory is handled gracefully with an error report."""
    result = FrontendScaffoldValidator.audit_scaffold(root_dir=tmp_path)

    assert result.is_valid is False
    assert len(result.missing_files) == len(FrontendScaffoldValidator.REQUIRED_FILES)
    assert result.wire_types_complete is False
    assert any("Desktop app directory missing" in issue for issue in result.issues)


def test_audit_scaffold_missing_file(tmp_path: Path) -> None:
    """Verifies that missing required files are flagged in the audit result."""
    desktop_dir = tmp_path / "apps" / "desktop"
    desktop_dir.mkdir(parents=True)

    # Populate only package.json
    pkg_path = desktop_dir / "package.json"
    pkg_path.write_text(
        json.dumps(
            {
                "name": "@system-mind/desktop",
                "version": "1.0.0",
                "scripts": {"dev": "vite", "build": "tsc", "test": "echo ok"},
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
            }
        ),
        encoding="utf-8",
    )

    result = FrontendScaffoldValidator.audit_scaffold(root_dir=tmp_path)
    assert result.is_valid is False
    assert "tsconfig.json" in result.missing_files
    assert "vite.config.ts" in result.missing_files
    assert any("tsconfig.json" in issue for issue in result.issues)


def test_audit_scaffold_prohibited_package(tmp_path: Path) -> None:
    """Verifies that attempting to import ambient execution packages fails the presentation boundary audit."""
    desktop_dir = tmp_path / "apps" / "desktop"
    src_types_dir = desktop_dir / "src" / "types"
    src_types_dir.mkdir(parents=True)

    # Copy minimal valid files
    for req in FrontendScaffoldValidator.REQUIRED_FILES:
        target = desktop_dir / req
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}", encoding="utf-8")

    # Contaminate package.json with prohibited ambient execution packages
    pkg_path = desktop_dir / "package.json"
    pkg_path.write_text(
        json.dumps(
            {
                "name": "@system-mind/desktop",
                "version": "1.0.0",
                "scripts": {"dev": "vite", "build": "tsc", "test": "echo ok"},
                "dependencies": {
                    "react": "^18.3.1",
                    "react-dom": "^18.3.1",
                    "execa": "^9.0.0",
                    "child_process": "latest",
                },
            }
        ),
        encoding="utf-8",
    )

    result = FrontendScaffoldValidator.audit_scaffold(root_dir=tmp_path)
    assert result.is_valid is False
    assert "execa" in result.prohibited_packages
    assert "child_process" in result.prohibited_packages
    assert any("prohibited package 'execa'" in issue for issue in result.issues)
    assert any("prohibited package 'child_process'" in issue for issue in result.issues)


def test_audit_scaffold_invalid_name_and_version(tmp_path: Path) -> None:
    """Verifies detection of non-compliant package name or invalid semver."""
    desktop_dir = tmp_path / "apps" / "desktop"
    desktop_dir.mkdir(parents=True)

    pkg_path = desktop_dir / "package.json"
    pkg_path.write_text(
        json.dumps(
            {
                "name": "random-ui-app",
                "version": "not-a-semver",
                "scripts": {"dev": "vite", "build": "tsc", "test": "echo ok"},
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
            }
        ),
        encoding="utf-8",
    )

    result = FrontendScaffoldValidator.audit_scaffold(root_dir=tmp_path)
    assert result.is_valid is False
    assert any("package.json name mismatch" in issue for issue in result.issues)
    assert any("invalid SemVer version" in issue for issue in result.issues)


def test_audit_scaffold_missing_script(tmp_path: Path) -> None:
    """Verifies detection of missing mandatory lifecycle scripts."""
    desktop_dir = tmp_path / "apps" / "desktop"
    desktop_dir.mkdir(parents=True)

    pkg_path = desktop_dir / "package.json"
    pkg_path.write_text(
        json.dumps(
            {
                "name": "@system-mind/desktop",
                "version": "1.0.0",
                "scripts": {"dev": "vite"},  # Missing "build" and "test"
                "dependencies": {"react": "^18.3.1", "react-dom": "^18.3.1"},
            }
        ),
        encoding="utf-8",
    )

    result = FrontendScaffoldValidator.audit_scaffold(root_dir=tmp_path)
    assert result.is_valid is False
    assert any("missing required script: 'build'" in issue for issue in result.issues)
    assert any("missing required script: 'test'" in issue for issue in result.issues)


def test_audit_scaffold_non_strict_tsconfig(tmp_path: Path) -> None:
    """Verifies detection of tsconfig.json without strict mode enabled."""
    desktop_dir = tmp_path / "apps" / "desktop"
    desktop_dir.mkdir(parents=True)

    ts_path = desktop_dir / "tsconfig.json"
    ts_path.write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "strict": False
                }
            }
        ),
        encoding="utf-8",
    )

    result = FrontendScaffoldValidator.audit_scaffold(root_dir=tmp_path)
    assert result.is_valid is False
    assert any("tsconfig.json must enforce 'strict: true'" in issue for issue in result.issues)


def test_verify_wire_types_contract_completeness() -> None:
    """Verifies wire type contract checker detects missing file trust or ownership states."""
    canonical_types = Path("apps/desktop/src/types/api.ts")
    ok, issues = FrontendScaffoldValidator.verify_wire_types(canonical_types)
    assert ok is True
    assert len(issues) == 0


def test_verify_wire_types_missing_variant(tmp_path: Path) -> None:
    """Verifies wire type checker flags omitted FileTrustState variants."""
    incomplete_types = tmp_path / "api.ts"
    incomplete_types.write_text(
        """
        export interface ApiRequest<T> { idempotency_key?: string; }
        export interface ApiResponse<T> {}
        export type FileTrustState = "QUARANTINED" | "VERIFIED";
        export type ComponentOwnership = "SYSTEM_MANAGED" | "VENDOR_MANAGED" | "USER_MANAGED";
        """,
        encoding="utf-8",
    )

    ok, issues = FrontendScaffoldValidator.verify_wire_types(incomplete_types)
    assert ok is False
    assert any("Missing FileTrustState variant 'SANDBOXED'" in issue for issue in issues)
    assert any("Missing FileTrustState variant 'STATIC_ANALYSIS_FAILED'" in issue for issue in issues)


def test_packaging_module_exports() -> None:
    """Verifies exports from packaging module."""
    from system_mind.packaging import FrontendScaffoldValidator as FSV
    from system_mind.packaging import FrontendScaffoldAuditResult as FSAR

    assert FSV is not None
    assert FSAR is not None
