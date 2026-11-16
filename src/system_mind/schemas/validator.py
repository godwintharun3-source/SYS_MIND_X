"""Validator enforcing JSON Schema specification compliance and polyglot cross-language parity."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import jsonschema

from system_mind.schemas.models import (
    CrossLanguageParityReport,
    ParityCheckResult,
    SchemaMetadata,
    SchemaValidationReport,
)


class SchemaStrategyValidator:
    """Validates canonical JSON Schemas and verifies cross-language enum and wire contract parity."""

    SCHEMAS_DIR = "schemas"

    REQUIRED_SCHEMAS = [
        "api_envelope.schema.json",
        "file_trust.schema.json",
        "component_ownership.schema.json",
        "action_contract.schema.json",
        "audit_event.schema.json",
        "monorepo.schema.json",
    ]

    @classmethod
    def load_json(cls, path: Path) -> Dict[str, Any]:
        """Loads and parses a JSON file."""
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def validate_all_schemas(cls, root_dir: Optional[Path] = None) -> SchemaValidationReport:
        """Validates all schema files against JSON Schema Draft specifications."""
        root = root_dir or Path.cwd()
        schemas_path = root / cls.SCHEMAS_DIR
        issues: List[str] = []
        verified: List[str] = []
        missing: List[str] = []

        if not schemas_path.exists() or not schemas_path.is_dir():
            return SchemaValidationReport(
                is_valid=False,
                schemas_checked_count=0,
                verified_schemas=[],
                missing_schemas=cls.REQUIRED_SCHEMAS,
                errors=[f"Schemas directory not found at: {schemas_path}"],
            )

        for filename in cls.REQUIRED_SCHEMAS:
            schema_file = schemas_path / filename
            if not schema_file.exists():
                missing.append(filename)
                issues.append(f"Required canonical schema missing: '{filename}'")
                continue

            try:
                schema_data = cls.load_json(schema_file)

                # Validate standard metadata fields
                if not schema_data.get("$schema"):
                    issues.append(f"Schema '{filename}' missing required '$schema' declaration")
                if not schema_data.get("$id"):
                    issues.append(f"Schema '{filename}' missing required '$id' URI")
                if not schema_data.get("title"):
                    issues.append(f"Schema '{filename}' missing required 'title'")
                if not schema_data.get("description"):
                    issues.append(f"Schema '{filename}' missing required 'description'")

                # Validate structural correctness using jsonschema Draft202012 / Draft7 validator
                jsonschema.Draft202012Validator.check_schema(schema_data)
                verified.append(filename)

            except Exception as e:
                issues.append(f"Invalid JSON Schema in '{filename}': {e}")

        is_valid = len(issues) == 0

        return SchemaValidationReport(
            is_valid=is_valid,
            schemas_checked_count=len(cls.REQUIRED_SCHEMAS),
            verified_schemas=verified,
            missing_schemas=missing,
            errors=issues,
        )

    @classmethod
    def verify_cross_language_parity(cls, root_dir: Optional[Path] = None) -> CrossLanguageParityReport:
        """Verifies that Python, TypeScript, and Rust type definitions match canonical schemas without drift."""
        root = root_dir or Path.cwd()
        schemas_path = root / cls.SCHEMAS_DIR
        issues: List[str] = []
        parity_results: Dict[str, ParityCheckResult] = {}

        # 1. Target files
        py_files = [
            root / "src" / "system_mind" / "core" / "types.py",
            root / "src" / "system_mind" / "files" / "models.py",
            root / "src" / "system_mind" / "api" / "models.py",
        ]
        ts_file = root / "apps" / "desktop" / "src" / "types" / "api.ts"
        rust_file = root / "crates" / "system-mind-common" / "src" / "types.rs"

        py_content = " ".join([f.read_text(encoding="utf-8") for f in py_files if f.exists()])
        ts_content = ts_file.read_text(encoding="utf-8") if ts_file.exists() else ""
        rust_content = rust_file.read_text(encoding="utf-8") if rust_file.exists() else ""

        # Enums to audit
        audit_targets = [
            ("file_trust.schema.json", "FileTrustState"),
            ("component_ownership.schema.json", "ComponentOwnership"),
        ]

        for schema_file, enum_name in audit_targets:
            schema_path = schemas_path / schema_file
            if not schema_path.exists():
                issues.append(f"Missing schema file '{schema_file}' for parity check")
                continue

            schema_data = cls.load_json(schema_path)
            defs = schema_data.get("$defs", {})
            enum_def = defs.get(enum_name, {})
            variants = enum_def.get("enum", [])

            missing_py: List[str] = []
            missing_ts: List[str] = []
            missing_rust: List[str] = []

            for var in variants:
                # Python check
                if f'"{var}"' not in py_content and f"'{var}'" not in py_content and var not in py_content:
                    missing_py.append(var)

                # TypeScript check
                if f'"{var}"' not in ts_content:
                    missing_ts.append(var)

                # Rust check: PascalCase variant
                pascal_var = "".join(part.capitalize() for part in var.split("_"))
                if pascal_var not in rust_content and var not in rust_content:
                    missing_rust.append(var)

            matches_py = len(missing_py) == 0
            matches_ts = len(missing_ts) == 0
            matches_rust = len(missing_rust) == 0

            if not matches_py:
                issues.append(f"Python missing {enum_name} variants: {missing_py}")
            if not matches_ts:
                issues.append(f"TypeScript missing {enum_name} variants: {missing_ts}")
            if not matches_rust:
                issues.append(f"Rust missing {enum_name} variants: {missing_rust}")

            parity_results[enum_name] = ParityCheckResult(
                type_name=enum_name,
                canonical_variants=variants,
                matches_python=matches_py,
                matches_typescript=matches_ts,
                matches_rust=matches_rust,
                missing_in_python=missing_py,
                missing_in_typescript=missing_ts,
                missing_in_rust=missing_rust,
            )

        is_valid = len(issues) == 0 and all(r.has_parity for r in parity_results.values())

        return CrossLanguageParityReport(
            is_valid=is_valid,
            enums_checked=list(parity_results.keys()),
            parity_results=parity_results,
            drift_issues=issues,
        )
