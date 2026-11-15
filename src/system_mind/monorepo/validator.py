"""Programmatic verification of monorepo boundaries, dependency rules, and workspace contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from system_mind.monorepo.models import (
    BoundaryAuditResult,
    MonorepoManifest,
    PrimaryLanguage,
    WorkspaceBoundarySpec,
    WorkspaceType,
)


class MonorepoBoundaryValidator:
    """Validates structural compliance and dependency isolation across monorepo workspaces."""

    DEFAULT_MANIFEST_FILENAME = "monorepo.json"

    @classmethod
    def load_manifest(cls, manifest_path: Optional[Path] = None) -> MonorepoManifest:
        """Load and parse the canonical monorepo.json manifest."""
        path = manifest_path or Path.cwd() / cls.DEFAULT_MANIFEST_FILENAME
        if not path.exists():
            raise FileNotFoundError(f"Monorepo manifest not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        boundaries: Dict[str, WorkspaceBoundarySpec] = {}
        for key, raw in data.get("root_boundaries", {}).items():
            boundaries[key] = WorkspaceBoundarySpec(
                name=key,
                path=raw["path"],
                workspace_type=WorkspaceType(raw["type"]),
                primary_language=PrimaryLanguage(raw["primary_language"]),
                layers=raw.get("layers", []),
                allowed_dependencies=raw.get("allowed_dependencies", []),
                forbidden_dependencies=raw.get("forbidden_dependencies", []),
                boundary_doc=raw["boundary_doc"],
                description=raw.get("description", ""),
            )

        return MonorepoManifest(
            name=data["name"],
            version=data["version"],
            monorepo_version=data["monorepo_version"],
            description=data.get("description", ""),
            root_boundaries=boundaries,
        )

    @classmethod
    def verify_dependency_rule(
        cls,
        source_workspace: str,
        target_workspace: str,
        manifest: Optional[MonorepoManifest] = None,
    ) -> bool:
        """Evaluate if an outbound dependency from source to target is permitted."""
        manifest = manifest or cls.load_manifest()

        if source_workspace not in manifest.root_boundaries:
            raise KeyError(f"Unknown source workspace: '{source_workspace}'")

        if source_workspace == target_workspace:
            return True  # Internal workspace dependencies are permitted

        src_spec = manifest.root_boundaries[source_workspace]

        if target_workspace in src_spec.forbidden_dependencies:
            return False

        if target_workspace in src_spec.allowed_dependencies:
            return True

        # Fail-closed: unlisted dependencies default to forbidden
        return False

    @classmethod
    def verify_structure(
        cls,
        repo_root: Optional[Path] = None,
        manifest: Optional[MonorepoManifest] = None,
    ) -> BoundaryAuditResult:
        """Perform full structural audit on workspace directories and boundary documentation."""
        root = repo_root or Path.cwd()
        manifest = manifest or cls.load_manifest(root / cls.DEFAULT_MANIFEST_FILENAME)

        missing_workspaces: List[str] = []
        missing_docs: List[str] = []
        verified_boundaries: List[str] = []
        issues: List[str] = []

        for name, spec in manifest.root_boundaries.items():
            ws_dir = root / spec.path
            if not ws_dir.exists() or not ws_dir.is_dir():
                missing_workspaces.append(name)
                issues.append(f"Workspace directory does not exist: '{spec.path}'")
                continue

            doc_path = root / spec.boundary_doc
            if not doc_path.exists() or not doc_path.is_file():
                missing_docs.append(name)
                issues.append(f"Workspace boundary documentation missing: '{spec.boundary_doc}'")
            else:
                verified_boundaries.append(name)

        # Invariant: verify at least the 6 core workspaces are registered
        expected_core = {"apps", "crates", "src", "schemas", "tools", "docs"}
        missing_core = expected_core - set(manifest.root_boundaries.keys())
        if missing_core:
            issues.append(f"Manifest missing core workspace declarations: {sorted(missing_core)}")

        is_valid = len(issues) == 0

        return BoundaryAuditResult(
            is_valid=is_valid,
            inspected_workspaces_count=len(manifest.root_boundaries),
            verified_boundaries=verified_boundaries,
            missing_workspaces=missing_workspaces,
            missing_boundary_docs=missing_docs,
            dependency_violations=[],
            issues=issues,
        )
