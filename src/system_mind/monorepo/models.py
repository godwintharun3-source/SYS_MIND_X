"""Data models and boundary specifications for the SYSTEM MIND X Monorepo."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class WorkspaceType(str, Enum):
    """Architectural classification of a monorepo workspace."""

    APPLICATION = "APPLICATION"
    SYSTEM_DAEMON_AND_SENSORS = "SYSTEM_DAEMON_AND_SENSORS"
    CONTROL_PLANE_AND_TWIN = "CONTROL_PLANE_AND_TWIN"
    SHARED_CONTRACTS = "SHARED_CONTRACTS"
    DEVELOPER_TOOLING = "DEVELOPER_TOOLING"
    DOCUMENTATION = "DOCUMENTATION"


class PrimaryLanguage(str, Enum):
    """Primary programming language or format of a workspace."""

    TYPESCRIPT = "TYPESCRIPT"
    RUST = "RUST"
    PYTHON = "PYTHON"
    SCHEMA_IDL = "SCHEMA_IDL"
    MARKDOWN = "MARKDOWN"


@dataclass(frozen=True)
class WorkspaceBoundarySpec:
    """Documented boundary contract for a top-level monorepo zone."""

    name: str
    path: str
    workspace_type: WorkspaceType
    primary_language: PrimaryLanguage
    layers: List[str]
    allowed_dependencies: List[str]
    forbidden_dependencies: List[str]
    boundary_doc: str
    description: str


@dataclass(frozen=True)
class MonorepoManifest:
    """Parsed representation of monorepo.json manifest."""

    name: str
    version: str
    monorepo_version: str
    description: str
    root_boundaries: Dict[str, WorkspaceBoundarySpec]


@dataclass(frozen=True)
class BoundaryAuditResult:
    """Outcome of monorepo boundary and structural verification."""

    is_valid: bool
    inspected_workspaces_count: int
    verified_boundaries: List[str]
    missing_workspaces: List[str]
    missing_boundary_docs: List[str]
    dependency_violations: List[str]
    issues: List[str] = field(default_factory=list)
