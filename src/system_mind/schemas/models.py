"""Data models and audit structures for schema validation and cross-language parity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class SchemaMetadata:
    """Metadata extracted from a canonical JSON Schema file."""

    schema_id: str
    title: str
    description: str
    file_path: str
    defs_count: int


@dataclass(frozen=True)
class SchemaValidationReport:
    """Audit report for JSON Schema validity across all schema files."""

    is_valid: bool
    schemas_checked_count: int
    verified_schemas: List[str]
    missing_schemas: List[str]
    errors: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParityCheckResult:
    """Comparison result for a single enum/type across Python, TypeScript, and Rust."""

    type_name: str
    canonical_variants: List[str]
    matches_python: bool
    matches_typescript: bool
    matches_rust: bool
    missing_in_python: List[str] = field(default_factory=list)
    missing_in_typescript: List[str] = field(default_factory=list)
    missing_in_rust: List[str] = field(default_factory=list)

    @property
    def has_parity(self) -> bool:
        return self.matches_python and self.matches_typescript and self.matches_rust


@dataclass(frozen=True)
class CrossLanguageParityReport:
    """Comprehensive cross-language parity audit across polyglot components."""

    is_valid: bool
    enums_checked: List[str]
    parity_results: Dict[str, ParityCheckResult]
    drift_issues: List[str] = field(default_factory=list)
