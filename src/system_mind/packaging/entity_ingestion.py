"""Packaging and safety invariant validator for Day 071 Entity Relationship Ingestion."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class EntityIngestionAuditResult:
    """Outcome of auditing Day 071 entity relationship ingestion components and invariants."""

    valid: bool
    issues: tuple[str, ...]
    ingestion_engine_present: bool
    design_note_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    functional_ingestion_valid: bool


class EntityIngestionValidator:
    """Audits the completeness, safety, and packaging of Day 071 entity relationship ingestion."""

    REQUIRED_FILES = [
        Path("src/system_mind/twin/ingestion.py"),
        Path("docs/design/DAY_071_ENTITY_RELATIONSHIP_INGESTION.md"),
        Path("tools/detect_entity_ingestion.py"),
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> EntityIngestionAuditResult:
        """Executes comprehensive packaging audit across entity relationship ingestion components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        ingestion_file = base / "src/system_mind/twin/ingestion.py"
        design_file = base / "docs/design/DAY_071_ENTITY_RELATIONSHIP_INGESTION.md"
        tool_file = base / "tools/detect_entity_ingestion.py"

        ingestion_engine_present = ingestion_file.is_file()
        design_note_present = design_file.is_file()
        tool_present = tool_file.is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # AST Safety Check on Python files (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_files = [ingestion_file, tool_file]
        for pf in python_files:
            if pf.is_file():
                try:
                    tree = ast.parse(pf.read_text(encoding="utf-8"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            if isinstance(node.func, ast.Attribute):
                                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                    if node.func.attr in ("system", "popen"):
                                        issues.append(f"Forbidden call to os.{node.func.attr} in {pf.name}")
                                        ast_safety_valid = False
                            for kw in node.keywords:
                                if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                    issues.append(f"Forbidden shell=True in {pf.name}")
                                    ast_safety_valid = False
                except Exception as e:
                    issues.append(f"Failed to parse AST of {pf.name}: {e}")
                    ast_safety_valid = False

        # Invariant checks on runtime models (SC-03: scan_proves_safe = False)
        charter_invariants_valid = True
        try:
            from system_mind.twin.ingestion import IngestionResult

            res = IngestionResult(
                ingestion_id="test-ingest",
                device_id="test-dev",
                timestamp_utc="2026-11-18T12:00:00Z",
                entities_ingested=0,
                relationships_ingested=0,
                entities=(),
                relationships=(),
                warnings=(),
            )
            if res.scan_proves_safe is not False:
                issues.append("IngestionResult violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            try:
                IngestionResult(
                    ingestion_id="test-ingest",
                    device_id="test-dev",
                    timestamp_utc="2026-11-18T12:00:00Z",
                    entities_ingested=0,
                    relationships_ingested=0,
                    entities=(),
                    relationships=(),
                    warnings=(),
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append("IngestionResult permitted scan_proves_safe=True")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correctly rejected
        except Exception as exc:
            issues.append(f"IngestionResult invariant check exception: {exc}")
            charter_invariants_valid = False

        # Functional Ingestion Check
        functional_ingestion_valid = True
        try:
            from system_mind.core.types import ComponentOwnership
            from system_mind.twin.graph import DigitalTwinGraph
            from system_mind.twin.ingestion import EntityRelationshipIngestor
            from system_mind.twin.models import TwinRelationType

            sample_sections: Dict[str, Any] = {
                "IDENTITY": {
                    "os_name": "macOS",
                    "os_version": "15.1",
                    "os_build": "24B83",
                    "kernel_release": "24.1.0",
                    "architecture": "arm64",
                    "host_name": "developer-macbook",
                },
                "HARDWARE": {
                    "cpu": {
                        "brand_string": "Apple M3 Pro",
                        "physical_cores": 12,
                        "logical_cores": 12,
                        "architecture": "arm64",
                    },
                    "memory": {
                        "total_bytes": 19327352832,
                        "page_size": 16384,
                    },
                    "gpu": {
                        "gpus": [{"model": "Apple M3 Pro GPU", "cores": 18, "metal_version": "Metal 3"}],
                    },
                },
                "STORAGE": {
                    "volumes": [
                        {
                            "volume_name": "Macintosh HD",
                            "mount_point": "/",
                            "fs_type": "apfs",
                            "total_bytes": 1000000000000,
                            "free_bytes": 600000000000,
                            "is_boot_volume": True,
                        }
                    ]
                },
                "NETWORK": {
                    "interfaces": [
                        {
                            "interface_name": "en0",
                            "mac_address_hash": "a1b2c3d4",
                            "ip_address": "192.168.1.50",
                            "link_state": "UP",
                        }
                    ]
                },
                "APPLICATIONS": {
                    "applications": [
                        {
                            "name": "Google Chrome",
                            "bundle_id": "com.google.Chrome",
                            "bundle_path": "/Applications/Google Chrome.app",
                            "version": "130.0.6723.117",
                            "ownership": ComponentOwnership.USER_MANAGED.value,
                            "is_user_app": True,
                            "is_apple": False,
                            "executable_name": "Google Chrome",
                        }
                    ]
                },
                "PROCESSES": {
                    "processes": [
                        {
                            "pid": 1,
                            "ppid": 0,
                            "name": "launchd",
                            "command_path": "/sbin/launchd",
                            "ownership": ComponentOwnership.SYSTEM_MANAGED.value,
                            "is_system_core": True,
                        },
                        {
                            "pid": 5001,
                            "ppid": 1,
                            "name": "Google Chrome",
                            "command_path": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                            "ownership": ComponentOwnership.USER_MANAGED.value,
                            "is_user_app": True,
                        },
                        {
                            "pid": 5002,
                            "ppid": 5001,
                            "name": "Google Chrome Helper",
                            "command_path": "/Applications/Google Chrome.app/Contents/Frameworks/Google Chrome Framework.framework/Helpers/Google Chrome Helper.app/Contents/MacOS/Google Chrome Helper",
                            "ownership": ComponentOwnership.USER_MANAGED.value,
                            "is_user_app": True,
                        },
                    ]
                },
                "SERVICES": {
                    "services": [
                        {
                            "label": "com.apple.Finder",
                            "domain": "system_agent",
                            "status": "RUNNING",
                            "program": "/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
                            "pid": 1,
                        }
                    ]
                },
            }

            test_graph = DigitalTwinGraph()
            ingestor = EntityRelationshipIngestor(device_id="8b14bd5b-dcd4-5d39-af4e-3e95c72e53ab")
            result = ingestor.ingest_sections(sections=sample_sections, graph=test_graph)

            if result.entities_ingested < 8:
                issues.append(f"Insufficient entities ingested: {result.entities_ingested} < 8")
                functional_ingestion_valid = False

            if result.relationships_ingested < 8:
                issues.append(f"Insufficient relationships ingested: {result.relationships_ingested} < 8")
                functional_ingestion_valid = False

            is_valid, violations = test_graph.validate_integrity()
            if not is_valid:
                issues.append(f"Graph integrity validation failed: {'; '.join(violations)}")
                functional_ingestion_valid = False

            # Verify process lineage relationship: 5002 -> SPAWNED_BY -> 5001
            spawned_rels = [
                r for r in result.relationships if r.relation_type == TwinRelationType.SPAWNED_BY
            ]
            if not spawned_rels:
                issues.append("Expected SPAWNED_BY relationship between child and parent processes")
                functional_ingestion_valid = False

            # Verify app ownership relationship: Chrome App -> OWNS -> Chrome Process
            owns_rels = [
                r for r in result.relationships if r.relation_type == TwinRelationType.OWNS
            ]
            if not owns_rels:
                issues.append("Expected OWNS relationship between Application and Process")
                functional_ingestion_valid = False

        except Exception as exc:
            issues.append(f"Functional ingestion check exception: {exc}")
            functional_ingestion_valid = False

        valid = (
            ingestion_engine_present
            and design_note_present
            and tool_present
            and ast_safety_valid
            and charter_invariants_valid
            and functional_ingestion_valid
            and len(issues) == 0
        )

        return EntityIngestionAuditResult(
            valid=valid,
            issues=tuple(issues),
            ingestion_engine_present=ingestion_engine_present,
            design_note_present=design_note_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            functional_ingestion_valid=functional_ingestion_valid,
        )
