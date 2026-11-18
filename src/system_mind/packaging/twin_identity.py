"""Packaging validator for Day 066 Digital Twin Stable Entity Identifiers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class TwinIdentityAuditResult:
    """Outcome of auditing the Digital Twin entity identity packaging and safety invariants."""

    valid: bool
    issues: tuple[str, ...]
    python_identity_present: bool
    rust_identity_present: bool
    design_note_present: bool
    tool_present: bool
    ast_safety_valid: bool
    charter_invariants_valid: bool
    domains_count: int


class TwinIdentityValidator:
    """Audits the completeness, safety, and packaging of Digital Twin entity identity."""

    REQUIRED_FILES = [
        Path("src/system_mind/twin/identity.py"),
        Path("src/system_mind/twin/__init__.py"),
        Path("crates/system-mind-common/src/identity.rs"),
        Path("crates/system-mind-common/src/lib.rs"),
        Path("docs/design/DAY_066_STABLE_DEVICE_AND_ENTITY_IDENTIFIERS.md"),
        Path("tools/detect_stable_identity.py"),
    ]

    CANONICAL_DOMAINS = [
        "host",
        "kernel",
        "cpu",
        "mem",
        "vol",
        "net",
        "app",
        "proc",
        "svc",
        "file",
        "pkg",
    ]

    @classmethod
    def audit(cls, root_dir: Optional[Path] = None) -> TwinIdentityAuditResult:
        """Executes comprehensive packaging audit across digital twin identity components."""
        base = root_dir or ROOT_DIR
        issues: List[str] = []

        python_identity_present = (base / "src/system_mind/twin/identity.py").is_file()
        rust_identity_present = (base / "crates/system-mind-common/src/identity.rs").is_file()
        design_note_present = (base / "docs/design/DAY_066_STABLE_DEVICE_AND_ENTITY_IDENTIFIERS.md").is_file()
        tool_present = (base / "tools/detect_stable_identity.py").is_file()

        for req in cls.REQUIRED_FILES:
            if not (base / req).is_file():
                issues.append(f"Missing required file: {req}")

        # AST Safety Check on Python module (SC-01: Zero ambient shell authority)
        ast_safety_valid = True
        python_file = base / "src/system_mind/twin/identity.py"
        if python_file.is_file():
            try:
                tree = ast.parse(python_file.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        # Detect os.system or os.popen
                        if isinstance(node.func, ast.Attribute):
                            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                                if node.func.attr in ("system", "popen"):
                                    issues.append(f"Forbidden call to os.{node.func.attr} in identity.py")
                                    ast_safety_valid = False
                        # Check subprocess.run shell=True
                        for kw in node.keywords:
                            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                                issues.append("Forbidden shell=True in subprocess call in identity.py")
                                ast_safety_valid = False
            except Exception as e:
                issues.append(f"Failed to parse AST of identity.py: {e}")
                ast_safety_valid = False
        else:
            ast_safety_valid = False

        # Invariant checks on runtime modules (SC-03: scan_proves_safe = False)
        charter_invariants_valid = True
        domains_count = 0
        try:
            from system_mind.twin.identity import EntityDomain, EntityUrn

            domains_count = len(list(EntityDomain))
            for expected_dom in cls.CANONICAL_DOMAINS:
                try:
                    EntityDomain(expected_dom)
                except ValueError:
                    issues.append(f"Missing expected canonical EntityDomain: {expected_dom}")
                    charter_invariants_valid = False

            test_urn = EntityUrn(EntityDomain.HOST, "test-qualifier", "urn:systemmind:host:test-qualifier")
            if test_urn.scan_proves_safe is not False:
                issues.append("EntityUrn violated charter invariant: scan_proves_safe is not False")
                charter_invariants_valid = False

            # Verify that setting scan_proves_safe=True raises ValueError
            try:
                EntityUrn(
                    EntityDomain.HOST,
                    "test",
                    "urn:systemmind:host:test",
                    scan_proves_safe=True,  # type: ignore[arg-type]
                )
                issues.append("EntityUrn permitted scan_proves_safe=True without raising ValueError")
                charter_invariants_valid = False
            except ValueError:
                pass  # Correct behaviour
        except Exception as e:
            issues.append(f"Failed to inspect identity module invariants: {e}")
            charter_invariants_valid = False

        valid = len(issues) == 0

        return TwinIdentityAuditResult(
            valid=valid,
            issues=tuple(issues),
            python_identity_present=python_identity_present,
            rust_identity_present=rust_identity_present,
            design_note_present=design_note_present,
            tool_present=tool_present,
            ast_safety_valid=ast_safety_valid,
            charter_invariants_valid=charter_invariants_valid,
            domains_count=domains_count,
        )
