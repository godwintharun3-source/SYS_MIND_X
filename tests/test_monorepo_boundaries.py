"""Unit and contract tests for SYSTEM MIND X Monorepo boundaries and workspace topology."""

import json
from pathlib import Path
import pytest
from system_mind.monorepo.models import (
    BoundaryAuditResult,
    MonorepoManifest,
    PrimaryLanguage,
    WorkspaceBoundarySpec,
    WorkspaceType,
)
from system_mind.monorepo.validator import MonorepoBoundaryValidator


def test_monorepo_manifest_loading():
    """Verify monorepo.json loads correctly with all 6 required top-level workspaces."""
    manifest = MonorepoBoundaryValidator.load_manifest()
    assert manifest.name == "system-mind-x"
    assert manifest.version == "1.0.0"
    assert manifest.monorepo_version == "1.0.0"
    assert len(manifest.root_boundaries) == 6

    expected_keys = {"apps", "crates", "src", "schemas", "tools", "docs"}
    assert set(manifest.root_boundaries.keys()) == expected_keys

    # Check specific workspace attributes
    crates_spec = manifest.root_boundaries["crates"]
    assert crates_spec.workspace_type == WorkspaceType.SYSTEM_DAEMON_AND_SENSORS
    assert crates_spec.primary_language == PrimaryLanguage.RUST
    assert "LAYER_6_TRUSTED_BROKER" in crates_spec.layers
    assert "src" in crates_spec.forbidden_dependencies
    assert crates_spec.boundary_doc == "crates/README.md"


def test_monorepo_structure_verification_passes():
    """Verify that current repository structure satisfies all monorepo boundary rules."""
    audit = MonorepoBoundaryValidator.verify_structure()
    assert audit.is_valid is True
    assert audit.inspected_workspaces_count == 6
    assert len(audit.verified_boundaries) == 6
    assert len(audit.missing_workspaces) == 0
    assert len(audit.missing_boundary_docs) == 0
    assert len(audit.issues) == 0


def test_dependency_direction_rules():
    """Verify strict unidirectional dependency rules across workspaces."""
    manifest = MonorepoBoundaryValidator.load_manifest()

    # Apps dependencies
    assert MonorepoBoundaryValidator.verify_dependency_rule("apps", "schemas", manifest) is True
    assert MonorepoBoundaryValidator.verify_dependency_rule("apps", "crates", manifest) is False
    assert MonorepoBoundaryValidator.verify_dependency_rule("apps", "src", manifest) is False
    assert MonorepoBoundaryValidator.verify_dependency_rule("apps", "apps", manifest) is True

    # Crates dependencies
    assert MonorepoBoundaryValidator.verify_dependency_rule("crates", "schemas", manifest) is True
    assert MonorepoBoundaryValidator.verify_dependency_rule("crates", "src", manifest) is False
    assert MonorepoBoundaryValidator.verify_dependency_rule("crates", "apps", manifest) is False

    # Src dependencies
    assert MonorepoBoundaryValidator.verify_dependency_rule("src", "schemas", manifest) is True
    assert MonorepoBoundaryValidator.verify_dependency_rule("src", "crates", manifest) is False
    assert MonorepoBoundaryValidator.verify_dependency_rule("src", "apps", manifest) is False

    # Schemas must be self-contained
    assert MonorepoBoundaryValidator.verify_dependency_rule("schemas", "apps", manifest) is False
    assert MonorepoBoundaryValidator.verify_dependency_rule("schemas", "crates", manifest) is False
    assert MonorepoBoundaryValidator.verify_dependency_rule("schemas", "src", manifest) is False

    # Unknown workspace raises KeyError
    with pytest.raises(KeyError, match="Unknown source workspace"):
        MonorepoBoundaryValidator.verify_dependency_rule("non_existent_workspace", "schemas", manifest)


def test_structure_verification_detects_missing_directory(tmp_path):
    """Verify validator flags missing workspace directories."""
    # Create incomplete repo mockup
    mock_manifest_data = {
        "name": "system-mind-x",
        "version": "1.0.0",
        "monorepo_version": "1.0.0",
        "root_boundaries": {
            "crates": {
                "path": "crates",
                "type": "SYSTEM_DAEMON_AND_SENSORS",
                "primary_language": "RUST",
                "layers": ["LAYER_6_TRUSTED_BROKER"],
                "allowed_dependencies": [],
                "forbidden_dependencies": ["src"],
                "boundary_doc": "crates/README.md",
                "description": "Rust crates",
            }
        },
    }
    manifest_file = tmp_path / "monorepo.json"
    manifest_file.write_text(json.dumps(mock_manifest_data), encoding="utf-8")

    manifest = MonorepoBoundaryValidator.load_manifest(manifest_file)
    audit = MonorepoBoundaryValidator.verify_structure(repo_root=tmp_path, manifest=manifest)

    assert audit.is_valid is False
    assert "crates" in audit.missing_workspaces
    assert any("Workspace directory does not exist" in issue for issue in audit.issues)


def test_structure_verification_detects_missing_boundary_doc(tmp_path):
    """Verify validator flags missing boundary documentation files."""
    # Create workspace dir without boundary doc
    (tmp_path / "apps").mkdir(parents=True)

    mock_manifest_data = {
        "name": "system-mind-x",
        "version": "1.0.0",
        "monorepo_version": "1.0.0",
        "root_boundaries": {
            "apps": {
                "path": "apps",
                "type": "APPLICATION",
                "primary_language": "TYPESCRIPT",
                "layers": ["LAYER_7_APPLICATION_PRESENTATION"],
                "allowed_dependencies": [],
                "forbidden_dependencies": [],
                "boundary_doc": "apps/README.md",
                "description": "Desktop apps",
            }
        },
    }
    manifest_file = tmp_path / "monorepo.json"
    manifest_file.write_text(json.dumps(mock_manifest_data), encoding="utf-8")

    manifest = MonorepoBoundaryValidator.load_manifest(manifest_file)
    audit = MonorepoBoundaryValidator.verify_structure(repo_root=tmp_path, manifest=manifest)

    assert audit.is_valid is False
    assert "apps" in audit.missing_boundary_docs
    assert any("boundary documentation missing" in issue for issue in audit.issues)


def test_monorepo_schema_file_is_valid_json():
    """Verify that schemas/monorepo.schema.json exists and is valid JSON."""
    schema_path = Path("schemas/monorepo.schema.json")
    assert schema_path.exists()
    assert schema_path.is_file()

    with open(schema_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["title"] == "MonorepoManifest"
    assert "root_boundaries" in data["required"]
