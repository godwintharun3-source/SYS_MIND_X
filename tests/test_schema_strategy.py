"""Unit and contract tests for canonical shared JSON schemas, type generation, and cross-language parity."""

import json
from pathlib import Path
import subprocess
import jsonschema
import pytest

from system_mind.schemas import (
    CrossLanguageParityReport,
    SchemaStrategyValidator,
    SchemaValidationReport,
    TypeGenerator,
)


def test_validate_all_canonical_schemas_pass() -> None:
    """Verifies that all canonical schema files pass strict JSON Schema specification audit."""
    report = SchemaStrategyValidator.validate_all_schemas()

    assert isinstance(report, SchemaValidationReport)
    assert report.is_valid is True
    assert len(report.verified_schemas) == len(SchemaStrategyValidator.REQUIRED_SCHEMAS)
    assert len(report.missing_schemas) == 0
    assert len(report.errors) == 0


def test_schema_validation_detects_missing_directory(tmp_path: Path) -> None:
    """Verifies that missing schemas directory is flagged gracefully in the audit report."""
    report = SchemaStrategyValidator.validate_all_schemas(root_dir=tmp_path)

    assert report.is_valid is False
    assert len(report.missing_schemas) == len(SchemaStrategyValidator.REQUIRED_SCHEMAS)
    assert any("Schemas directory not found" in err for err in report.errors)


def test_schema_validation_detects_missing_metadata(tmp_path: Path) -> None:
    """Verifies that schema files missing required metadata ($id, title, description) are flagged."""
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir(parents=True)

    for req in SchemaStrategyValidator.REQUIRED_SCHEMAS:
        schema_file = schemas_dir / req
        # Write schema missing $id and description
        schema_file.write_text(
            json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "title": "Incomplete"}),
            encoding="utf-8",
        )

    report = SchemaStrategyValidator.validate_all_schemas(root_dir=tmp_path)
    assert report.is_valid is False
    assert any("missing required '$id' URI" in err for err in report.errors)
    assert any("missing required 'description'" in err for err in report.errors)


def test_cross_language_parity_verification_passes() -> None:
    """Verifies that current repository Python, TypeScript, and Rust type definitions match canonical schemas."""
    parity_report = SchemaStrategyValidator.verify_cross_language_parity()

    assert isinstance(parity_report, CrossLanguageParityReport)
    assert parity_report.is_valid is True
    assert "FileTrustState" in parity_report.enums_checked
    assert "ComponentOwnership" in parity_report.enums_checked
    assert len(parity_report.drift_issues) == 0

    for enum_name, result in parity_report.parity_results.items():
        assert result.has_parity is True
        assert len(result.missing_in_python) == 0
        assert len(result.missing_in_typescript) == 0
        assert len(result.missing_in_rust) == 0


def test_cross_language_parity_detects_drift(tmp_path: Path) -> None:
    """Verifies that enum drift in target language files is detected and reported."""
    # Copy valid schemas
    schemas_dir = tmp_path / "schemas"
    schemas_dir.mkdir(parents=True)
    real_schemas = Path("schemas")
    for s in SchemaStrategyValidator.REQUIRED_SCHEMAS:
        (schemas_dir / s).write_text((real_schemas / s).read_text(encoding="utf-8"), encoding="utf-8")

    # Mock python file with missing variants
    py_dir = tmp_path / "src" / "system_mind" / "core"
    py_dir.mkdir(parents=True)
    (py_dir / "types.py").write_text('ComponentOwnership = ["SYSTEM_MANAGED"]', encoding="utf-8")

    # Mock TS file
    ts_dir = tmp_path / "apps" / "desktop" / "src" / "types"
    ts_dir.mkdir(parents=True)
    (ts_dir / "api.ts").write_text('export type ComponentOwnership = "SYSTEM_MANAGED";', encoding="utf-8")

    # Mock Rust file
    rust_dir = tmp_path / "crates" / "system-mind-common" / "src"
    rust_dir.mkdir(parents=True)
    (rust_dir / "types.rs").write_text("pub enum ComponentOwnership { SystemManaged }", encoding="utf-8")

    report = SchemaStrategyValidator.verify_cross_language_parity(root_dir=tmp_path)
    assert report.is_valid is False
    assert any("Python missing ComponentOwnership variants" in issue for issue in report.drift_issues)
    assert any("TypeScript missing ComponentOwnership variants" in issue for issue in report.drift_issues)
    assert any("Rust missing ComponentOwnership variants" in issue for issue in report.drift_issues)


def test_jsonschema_instance_validation_api_envelope() -> None:
    """Verifies instance validation using jsonschema validator on api_envelope.schema.json."""
    schema_path = Path("schemas/api_envelope.schema.json")
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))

    req_validator = jsonschema.Draft202012Validator(schema_data["$defs"]["ApiRequest"])

    # Valid ApiRequest instance
    valid_request = {
        "version": "1.0.0",
        "request_id": "req-12345",
        "timestamp": "2026-11-16T11:00:00Z",
        "caller_identity": "operator:console",
        "operation": "governance.evaluate_boundary",
        "payload": {"target": "user_apps"},
        "idempotency_key": "idemp-987654321",
    }
    req_validator.validate(valid_request)

    # Invalid ApiRequest: invalid operation pattern (uppercase not allowed)
    invalid_request = {
        "version": "1.0.0",
        "request_id": "req-12345",
        "timestamp": "2026-11-16T11:00:00Z",
        "caller_identity": "operator:console",
        "operation": "INVALID_OPERATION",
        "payload": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        req_validator.validate(invalid_request)


def test_jsonschema_instance_validation_file_trust_sc03() -> None:
    """Verifies that file_trust.schema.json validates valid states and blocks unknown/forged states."""
    schema_path = Path("schemas/file_trust.schema.json")
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))

    # Valid FileTrust instance
    valid_instance = {
        "path": "/opt/payloads/sample.bin",
        "trust_state": "QUARANTINED",
        "handler_mode": "DISPOSABLE_SANDBOX_EXECUTION",
        "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "quarantined": True,
        "last_inspected": "2026-11-16T11:00:00Z",
        "justification": "Untrusted external payload must be sandboxed.",
    }
    jsonschema.validate(instance=valid_instance, schema=schema_data)

    # Invalid FileTrust: attempting to forge state "SAFE" (violates SC-03)
    invalid_instance = {
        "path": "/opt/payloads/sample.bin",
        "trust_state": "SAFE",  # Illegal!
        "handler_mode": "NATIVE_HOST_EXECUTION",
        "sha256_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "last_inspected": "2026-11-16T11:00:00Z",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_instance, schema=schema_data)


def test_type_generator_bundle() -> None:
    """Verifies that TypeGenerator generates valid syntax bundles for TypeScript, Python, and Rust."""
    generator = TypeGenerator()
    bundle = generator.generate_bundle()

    assert "typescript" in bundle
    assert "python" in bundle
    assert "rust" in bundle

    # TypeScript checks
    assert 'export type FileTrustState =' in bundle["typescript"]
    assert '"UNTRUSTED_UNKNOWN"' in bundle["typescript"]
    assert '"QUARANTINED"' in bundle["typescript"]
    assert '"SYSTEM_MANAGED"' in bundle["typescript"]
    assert '"E1000"' in bundle["typescript"]

    # Python checks
    assert "class FileTrustState(str, Enum):" in bundle["python"]
    assert 'UNTRUSTED_UNKNOWN = "UNTRUSTED_UNKNOWN"' in bundle["python"]
    assert "class ComponentOwnership(str, Enum):" in bundle["python"]

    # Rust checks
    assert "pub enum FileTrustState {" in bundle["rust"]
    assert "UntrustedUnknown," in bundle["rust"]
    assert "Quarantined," in bundle["rust"]
    assert "pub enum ComponentOwnership {" in bundle["rust"]
    assert "SystemManaged," in bundle["rust"]


def test_generate_types_cli_dry_run() -> None:
    """Verifies that tools/generate_types.py --check executes cleanly and exits with status 0."""
    proc = subprocess.run(
        ["python3", "tools/generate_types.py", "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"generate_types.py failed:\n{proc.stdout}\n{proc.stderr}"
    assert "All 6 canonical schemas passed validation" in proc.stdout
    assert "Cross-language parity verified across" in proc.stdout
