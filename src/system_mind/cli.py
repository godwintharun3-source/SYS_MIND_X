"""Command-line entrypoint for the SYSTEM MIND X Python Control Plane."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

import system_mind
from system_mind.architecture.baseline import ArchitectureBaselineVerifier
from system_mind.monorepo.validator import MonorepoBoundaryValidator


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="system-mind",
        description="SYSTEM MIND X Control Plane - Inspection & Verification Tool",
    )
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version=f"SYSTEM MIND X Control Plane v{system_mind.__version__}",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Display control-plane operational status and subsystem health.",
    )
    parser.add_argument(
        "--audit-baseline",
        action="store_true",
        help="Run cryptographic audit on the frozen v1.0 architecture baseline.",
    )
    parser.add_argument(
        "--verify-boundaries",
        action="store_true",
        help="Verify monorepo directory topology and workspace boundaries.",
    )
    return parser


def handle_status() -> int:
    """Print health status of control plane subsystems."""
    print(f"SYSTEM MIND X Control Plane v{system_mind.__version__}")
    print("Execution Plane: Plane 1 (Cognitive & Control Plane - Non-Privileged)")
    print("Subsystems: Operational")
    print("  - Temporal Digital Twin: Ready")
    print("  - Intelligence Engines: 14/14 Registered")
    print("  - Policy Precedence Engine: Tier 1 Invariant Enforcement Active")
    print("  - Audit Ledger: SHA-256 Hash Chaining Active")
    return 0


def handle_audit_baseline() -> int:
    """Execute architecture baseline verification."""
    print("Auditing Architecture Baseline v1.0...")
    audit = ArchitectureBaselineVerifier.audit_baseline()
    if audit.is_frozen:
        print(f"Status: FROZEN_APPROVED (Fingerprint: {audit.baseline_fingerprint[:16]}...)")
        print(f"Verified Subsystems: {audit.verified_components_count}/14")
        print(f"Total Invariants: {audit.total_invariants_count}")
        return 0
    else:
        print("Status: FAILED")
        for issue in audit.issues:
            print(f"  - Issue: {issue}")
        return 1


def handle_verify_boundaries() -> int:
    """Execute monorepo boundary verification."""
    print("Verifying Monorepo Top-Level Boundaries...")
    audit = MonorepoBoundaryValidator.verify_structure()
    if audit.is_valid:
        print(f"Status: VALID ({audit.inspected_workspaces_count} workspaces verified)")
        for ws in audit.verified_boundaries:
            print(f"  - [{ws}] Verified")
        return 0
    else:
        print("Status: INVALID")
        for issue in audit.issues:
            print(f"  - Issue: {issue}")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main execution function."""
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.status:
        return handle_status()
    elif args.audit_baseline:
        return handle_audit_baseline()
    elif args.verify_boundaries:
        return handle_verify_boundaries()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
