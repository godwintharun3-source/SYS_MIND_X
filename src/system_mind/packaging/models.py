"""Data models and validation results for Python backend packaging."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PackageMetadata:
    """Extracted metadata from pyproject.toml."""

    name: str
    version: str
    requires_python: str
    scripts: Dict[str, str]
    dependencies: List[str]
    dev_dependencies: List[str]


@dataclass(frozen=True)
class PackageVerificationResult:
    """Formal audit report for Python package configuration compliance."""

    is_valid: bool
    name: str
    version: str
    requires_python: str
    entrypoint_valid: bool
    unpinned_dependencies: List[str]
    prohibited_dependencies: List[str]
    issues: List[str] = field(default_factory=list)
