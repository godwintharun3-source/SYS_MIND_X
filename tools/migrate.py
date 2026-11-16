#!/usr/bin/env python3
"""Unified SQLite database migration and schema management CLI for SYSTEM MIND X."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure src/ is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from system_mind.database.connection import DatabaseConfig
from system_mind.database.migrations import MIGRATIONS_DIR
from system_mind.database.migrator import DatabaseMigrator
from system_mind.database.models import MigrationDirection


def get_migrator(args: argparse.Namespace) -> DatabaseMigrator:
    """Builds and returns a DatabaseMigrator from CLI arguments."""
    migrations_dir = Path(args.migrations_dir).resolve() if args.migrations_dir else MIGRATIONS_DIR
    config = DatabaseConfig(db_path=args.db)
    return DatabaseMigrator(
        db_path=args.db,
        migrations_dir=migrations_dir,
        config=config,
    )


def cmd_status(args: argparse.Namespace) -> int:
    """Displays current database migration and integrity status."""
    migrator = get_migrator(args)
    applied = migrator.get_applied_migrations()
    registered = migrator.get_registered_migrations()
    integrity = migrator.verify_integrity()

    applied_versions = {a.version for a in applied}
    pending = [m for m in registered if m.version not in applied_versions]

    if args.json:
        payload = {
            "db_path": args.db,
            "latest_version": integrity.latest_version,
            "applied_count": len(applied),
            "pending_count": len(pending),
            "integrity_valid": integrity.valid,
            "applied": [a.to_dict() for a in applied],
            "pending": [{"version": p.version, "name": p.name} for p in pending],
            "issues": list(integrity.issues),
        }
        print(json.dumps(payload, indent=2))
        return 0 if integrity.valid else 1

    print(f"[*] Database: {args.db}")
    print(f"[*] Applied migrations: {len(applied)} | Pending: {len(pending)}")
    print(f"[*] Integrity: {'VALID' if integrity.valid else 'INVALID'}")
    print("-----------------------------------------------------------------")
    print(f"{'Version':<10} {'Name':<35} {'Status':<10} {'Applied At':<26}")
    print("-----------------------------------------------------------------")

    for a in applied:
        print(f"{a.version:<10} {a.name:<35} {'APPLIED':<10} {a.applied_at:<26}")
    for p in pending:
        print(f"{p.version:<10} {p.name:<35} {'PENDING':<10} {'-':<26}")

    if integrity.issues:
        print("\n[!] Integrity Issues:")
        for issue in integrity.issues:
            print(f"    - {issue}")
        return 1

    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Previews pending migration actions without modifying the database."""
    migrator = get_migrator(args)
    direction = MigrationDirection(args.direction.upper())
    plan = migrator.plan(direction=direction, target_version=args.target)

    if args.json:
        payload = {
            "direction": plan.direction.value,
            "target_version": plan.target_version,
            "is_noop": plan.is_noop,
            "migrations": [
                {"version": m.version, "name": m.name, "checksum": m.checksum}
                for m in plan.migrations
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    print(f"[*] Direction: {plan.direction.value} | Target version: {plan.target_version or 'all'}")
    print(f"[*] {plan.summary()}")
    for m in plan.migrations:
        print(f"    -> {m.version:04d}_{m.name} [checksum: {m.checksum[:12]}...]")

    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Applies pending migrations in forward direction."""
    migrator = get_migrator(args)
    conn = migrator._get_connection()
    try:
        plan = migrator.plan(MigrationDirection.UP, target_version=args.target, conn=conn)

        if plan.is_noop:
            if args.json:
                print(json.dumps({"applied": [], "message": "Database is already up to date."}))
            else:
                print("[+] Database is already up to date. No migrations to apply.")
            return 0

        applied_records = []
        for m in plan.migrations:
            record = migrator.apply_migration(m.version, conn=conn)
            applied_records.append(record)
            if not args.json:
                print(
                    f"[+] Applied {record.version:04d}_{record.name} "
                    f"({record.execution_time_ms:.1f}ms) [{record.checksum[:12]}...]"
                )

        if args.json:
            print(json.dumps({"applied": [r.to_dict() for r in applied_records]}, indent=2))

        return 0
    finally:
        conn.close()


def cmd_rollback(args: argparse.Namespace) -> int:
    """Rolls back applied migrations in reverse direction."""
    migrator = get_migrator(args)
    conn = migrator._get_connection()
    try:
        if args.target is not None:
            rolled_back = migrator.rollback_to(args.target, conn=conn)
        else:
            rec = migrator.rollback_last(conn=conn)
            rolled_back = [rec] if rec else []

        if not rolled_back:
            if args.json:
                print(json.dumps({"rolled_back": [], "message": "No migrations to roll back."}))
            else:
                print("[*] No migrations to roll back.")
            return 0

        if not args.json:
            for r in rolled_back:
                print(f"[-] Rolled back {r.version:04d}_{r.name} [{r.checksum[:12]}...]")
        else:
            print(json.dumps({"rolled_back": [r.to_dict() for r in rolled_back]}, indent=2))

        return 0
    finally:
        conn.close()


def cmd_verify(args: argparse.Namespace) -> int:
    """Verifies schema checksums, referential integrity, and SQLite PRAGMAs."""
    migrator = get_migrator(args)
    report = migrator.verify_integrity()

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.valid else 1

    print(f"[*] Database: {args.db}")
    print(f"[*] Applied count: {report.applied_count} | Pending count: {report.pending_count}")
    print(f"[*] Latest schema version: {report.latest_version or 'None'}")
    print(f"[*] Integrity verification: {'PASSED' if report.valid else 'FAILED'}")

    if report.issues:
        print("\n[!] Violations:")
        for issue in report.issues:
            print(f"    - {issue}")
        return 1

    print("[+] All checksums, sequence orders, foreign keys, and PRAGMA checks verified cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X SQLite Database Migration & Schema Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db",
        default=":memory:",
        help="Target SQLite database path or ':memory:'",
    )
    parser.add_argument(
        "--migrations-dir",
        default=None,
        help="Custom migrations directory containing SQL files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in structured JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # status
    subparsers.add_parser("status", help="Show migration status and applied history")

    # plan
    plan_parser = subparsers.add_parser("plan", help="Preview pending migrations")
    plan_parser.add_argument(
        "--direction",
        choices=["up", "down"],
        default="up",
        help="Planning direction",
    )
    plan_parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="Target migration version",
    )

    # apply
    apply_parser = subparsers.add_parser("apply", help="Apply pending migrations")
    apply_parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="Target migration version to apply up to",
    )

    # rollback
    rollback_parser = subparsers.add_parser("rollback", help="Roll back migrations")
    rollback_parser.add_argument(
        "--target",
        type=int,
        default=None,
        help="Target migration version to roll back down to (omit to rollback 1)",
    )

    # verify
    subparsers.add_parser("verify", help="Verify schema checksums and database integrity")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "plan": cmd_plan,
        "apply": cmd_apply,
        "rollback": cmd_rollback,
        "verify": cmd_verify,
    }

    handler = commands.get(args.command)
    if not handler:
        parser.print_help()
        return 1

    try:
        return handler(args)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
        else:
            print(f"[!] Migration error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
