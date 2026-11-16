"""Validator for the Rust system-agent workspace, Cargo manifest, and crate boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CrateBoundarySpec:
    """Documented boundaries and dependency rules for a Rust crate."""

    name: str
    path: str
    role: str
    allowed_internal_deps: List[str]
    prohibited_internal_deps: List[str]


@dataclass(frozen=True)
class RustWorkspaceAuditResult:
    """Audit outcome for Cargo workspace and crate boundaries."""

    is_valid: bool
    workspace_members_count: int
    verified_crates: List[str]
    missing_crates: List[str]
    prohibited_dependencies: List[str]
    issues: List[str] = field(default_factory=list)


class RustWorkspaceValidator:
    """Enforces crate boundaries, Cargo workspace configuration, and acyclic dependencies."""

    EXPECTED_MEMBERS = [
        "crates/system-mind-common",
        "crates/system-mind-sensors",
        "crates/system-mind-broker",
    ]

    CRATE_SPECS: Dict[str, CrateBoundarySpec] = {
        "system-mind-common": CrateBoundarySpec(
            name="system-mind-common",
            path="crates/system-mind-common",
            role="Core types and hashing",
            allowed_internal_deps=[],
            prohibited_internal_deps=["system-mind-sensors", "system-mind-broker"],
        ),
        "system-mind-sensors": CrateBoundarySpec(
            name="system-mind-sensors",
            path="crates/system-mind-sensors",
            role="Hardware telemetry and sensor collection",
            allowed_internal_deps=["system-mind-common"],
            prohibited_internal_deps=["system-mind-broker"],
        ),
        "system-mind-broker": CrateBoundarySpec(
            name="system-mind-broker",
            path="crates/system-mind-broker",
            role="Narrow privileged capability broker daemon",
            allowed_internal_deps=["system-mind-common", "system-mind-sensors"],
            prohibited_internal_deps=[],
        ),
    }

    @classmethod
    def load_root_cargo_toml(cls, root_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Parse root Cargo.toml manifest."""
        root = root_dir or Path.cwd()
        cargo_path = root / "Cargo.toml"
        if not cargo_path.exists():
            raise FileNotFoundError(f"Root Cargo.toml not found at: {cargo_path}")

        with open(cargo_path, "rb") as f:
            return tomllib.load(f)

    @classmethod
    def load_crate_cargo_toml(cls, crate_dir: Path) -> Dict[str, Any]:
        """Parse crate Cargo.toml manifest."""
        cargo_path = crate_dir / "Cargo.toml"
        if not cargo_path.exists():
            raise FileNotFoundError(f"Crate Cargo.toml not found at: {cargo_path}")

        with open(cargo_path, "rb") as f:
            return tomllib.load(f)

    @classmethod
    def audit_workspace(cls, root_dir: Optional[Path] = None) -> RustWorkspaceAuditResult:
        """Execute compliance audit on Cargo workspace members and crate boundaries."""
        root = root_dir or Path.cwd()
        issues: List[str] = []
        verified: List[str] = []
        missing: List[str] = []
        prohibited_deps: List[str] = []

        # 1. Root Cargo.toml inspection
        try:
            root_manifest = cls.load_root_cargo_toml(root)
        except Exception as e:
            return RustWorkspaceAuditResult(
                is_valid=False,
                workspace_members_count=0,
                verified_crates=[],
                missing_crates=cls.EXPECTED_MEMBERS,
                prohibited_dependencies=[],
                issues=[str(e)],
            )

        workspace = root_manifest.get("workspace", {})
        members = workspace.get("members", [])

        for expected in cls.EXPECTED_MEMBERS:
            if expected not in members:
                issues.append(f"Root Cargo.toml missing workspace member: '{expected}'")

        # 2. Crate manifests and boundary dependency validation
        for crate_name, spec in cls.CRATE_SPECS.items():
            crate_path = root / spec.path
            if not crate_path.exists() or not crate_path.is_dir():
                missing.append(crate_name)
                issues.append(f"Crate directory missing: '{spec.path}'")
                continue

            try:
                crate_toml = cls.load_crate_cargo_toml(crate_path)
            except Exception as e:
                missing.append(crate_name)
                issues.append(f"Failed to load crate manifest for '{crate_name}': {e}")
                continue

            pkg_name = crate_toml.get("package", {}).get("name", "")
            if pkg_name != crate_name:
                issues.append(
                    f"Crate name mismatch in '{spec.path}/Cargo.toml': found '{pkg_name}', expected '{crate_name}'"
                )

            deps = crate_toml.get("dependencies", {})
            for prohibited in spec.prohibited_internal_deps:
                if prohibited in deps:
                    prohibited_deps.append(f"{crate_name} -> {prohibited}")
                    issues.append(
                        f"Boundary violation: Crate '{crate_name}' illegally depends on prohibited crate '{prohibited}'"
                    )

            verified.append(crate_name)

        is_valid = len(issues) == 0

        return RustWorkspaceAuditResult(
            is_valid=is_valid,
            workspace_members_count=len(members),
            verified_crates=verified,
            missing_crates=missing,
            prohibited_dependencies=prohibited_deps,
            issues=issues,
        )
