"""Multi-language type generator translating JSON Schema contracts to Python, TypeScript, and Rust."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class TypeGenerator:
    """Generates strongly typed declarations from canonical JSON Schemas."""

    def __init__(self, schemas_dir: Optional[Path] = None):
        self.schemas_dir = schemas_dir or (Path.cwd() / "schemas")

    def load_schema(self, schema_filename: str) -> Dict[str, Any]:
        """Loads and parses a schema file from the schemas directory."""
        path = self.schemas_dir / schema_filename
        if not path.exists():
            raise FileNotFoundError(f"Schema not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def extract_enum(self, schema_filename: str, def_name: str) -> List[str]:
        """Extracts enum variants from a schema definition."""
        schema = self.load_schema(schema_filename)
        defs = schema.get("$defs", {})
        target = defs.get(def_name, {})
        variants = target.get("enum", [])
        if not variants:
            raise ValueError(f"Definition '{def_name}' in '{schema_filename}' is not an enum or has no variants.")
        return list(variants)

    def generate_typescript_enum(self, enum_name: str, variants: List[str]) -> str:
        """Generates TypeScript union type string."""
        lines = [f"export type {enum_name} ="]
        for v in variants:
            lines.append(f'  | "{v}"')
        lines[-1] += ";"
        return "\n".join(lines)

    def generate_python_enum(self, enum_name: str, variants: List[str]) -> str:
        """Generates Python Enum class string."""
        lines = [
            f"class {enum_name}(str, Enum):",
            f'    """Generated canonical enum for {enum_name}."""',
        ]
        for v in variants:
            lines.append(f'    {v} = "{v}"')
        return "\n".join(lines)

    def generate_rust_enum(self, enum_name: str, variants: List[str]) -> str:
        """Generates Rust enum definition with PascalCase variants."""
        lines = [
            "#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]",
            f"pub enum {enum_name} {{",
        ]
        for v in variants:
            # Convert SNAKE_CASE or UPPER_CASE to PascalCase for Rust
            pascal_variant = "".join(part.capitalize() for part in v.split("_"))
            lines.append(f"    {pascal_variant},")
        lines.append("}")
        return "\n".join(lines)

    def generate_bundle(self) -> Dict[str, str]:
        """Generates a complete bundle of canonical type definitions for all targets."""
        # 1. FileTrustState
        file_trust_variants = self.extract_enum("file_trust.schema.json", "FileTrustState")
        # 2. ComponentOwnership
        ownership_variants = self.extract_enum("component_ownership.schema.json", "ComponentOwnership")
        # 3. ErrorCode
        error_code_variants = self.extract_enum("api_envelope.schema.json", "ErrorCode")

        ts_output = "\n\n".join([
            "// AUTO-GENERATED FROM CANONICAL JSON SCHEMAS. DO NOT EDIT DIRECTLY.",
            self.generate_typescript_enum("FileTrustState", file_trust_variants),
            self.generate_typescript_enum("ComponentOwnership", ownership_variants),
            self.generate_typescript_enum("ErrorCode", error_code_variants),
        ])

        py_output = "\n\n".join([
            "# AUTO-GENERATED FROM CANONICAL JSON SCHEMAS. DO NOT EDIT DIRECTLY.",
            "from enum import Enum",
            self.generate_python_enum("FileTrustState", file_trust_variants),
            self.generate_python_enum("ComponentOwnership", ownership_variants),
            self.generate_python_enum("ErrorCode", error_code_variants),
        ])

        rust_output = "\n\n".join([
            "// AUTO-GENERATED FROM CANONICAL JSON SCHEMAS. DO NOT EDIT DIRECTLY.",
            self.generate_rust_enum("FileTrustState", file_trust_variants),
            self.generate_rust_enum("ComponentOwnership", ownership_variants),
            self.generate_rust_enum("ErrorCode", error_code_variants),
        ])

        return {
            "typescript": ts_output,
            "python": py_output,
            "rust": rust_output,
        }
