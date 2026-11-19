#!/usr/bin/env python3
"""Unified local continuous integration runner for SYSTEM MIND X."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from system_mind.packaging.dependency_review import DependencyReviewer


def _run_stage(name: str, cmd: list[str], dry_run: bool = False) -> dict[str, Any]:
    """Executes a CI stage with telemetry and error containment."""
    if dry_run:
        return {
            "stage": name,
            "status": "SKIPPED_DRY_RUN",
            "exit_code": 0,
            "duration_s": 0.0,
            "command": " ".join(cmd),
        }

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        duration = time.perf_counter() - start
        return {
            "stage": name,
            "status": "PASSED" if proc.returncode == 0 else "FAILED",
            "exit_code": proc.returncode,
            "duration_s": round(duration, 2),
            "command": " ".join(cmd),
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as e:
        duration = time.perf_counter() - start
        return {
            "stage": name,
            "status": "ERROR",
            "exit_code": 1,
            "duration_s": round(duration, 2),
            "command": " ".join(cmd),
            "stderr": str(e),
        }


def run_dependency_review(dry_run: bool = False) -> dict[str, Any]:
    """Executes dependency supply-chain security audit."""
    if dry_run:
        return {
            "stage": "dependency-review",
            "status": "SKIPPED_DRY_RUN",
            "exit_code": 0,
            "duration_s": 0.0,
        }

    start = time.perf_counter()
    result = DependencyReviewer.audit(ROOT_DIR)
    duration = time.perf_counter() - start

    return {
        "stage": "dependency-review",
        "status": "PASSED" if result.valid else "FAILED",
        "exit_code": 0 if result.valid else 1,
        "duration_s": round(duration, 2),
        "issues": list(result.issues),
        "summary": (
            f"Audited {len(result.scanned_files)} manifests "
            f"({result.python_packages_count} Python, "
            f"{result.rust_crates_count} Rust, "
            f"{result.node_packages_count} Node)"
        ),
    }


def cmd_lint(args: argparse.Namespace) -> int:
    """Executes linting, AST safety, secrets scanning, and schema parity stages."""
    dry_run = args.dry_run
    results: list[dict[str, Any]] = []

    # 1. Multi-language linting and AST safety
    lint_py = ROOT_DIR / "tools" / "lint.py"
    res_lint = _run_stage("lint-and-ast-safety", [sys.executable, str(lint_py)], dry_run)
    results.append(res_lint)

    # 2. Shared schemas cross-language parity
    types_py = ROOT_DIR / "tools" / "generate_types.py"
    res_types = _run_stage("schemas-parity-check", [sys.executable, str(types_py), "--check"], dry_run)
    results.append(res_types)

    return _process_results("Lint and Safety", results, args.json)


def cmd_test(args: argparse.Namespace) -> int:
    """Executes polyglot test suites."""
    dry_run = args.dry_run
    test_runner_py = ROOT_DIR / "tools" / "test_runner.py"
    res_test = _run_stage("polyglot-test-suites", [sys.executable, str(test_runner_py), "--all"], dry_run)
    return _process_results("Polyglot Tests", [res_test], args.json)


def cmd_deps(args: argparse.Namespace) -> int:
    """Executes dependency review."""
    res_deps = run_dependency_review(args.dry_run)

    if args.json:
        print(json.dumps(res_deps, indent=2))
        return res_deps["exit_code"]

    print("[*] SYSTEM MIND X — Dependency & Supply-Chain Review")
    print(f"[*] Status: {res_deps['status']} ({res_deps['duration_s']}s)")
    if "summary" in res_deps:
        print(f"[*] {res_deps['summary']}")

    if res_deps.get("issues"):
        print("\n[!] Violations Detected:")
        for issue in res_deps["issues"]:
            print(f"    - {issue}")
        return 1

    print("[+] All package manifests declare strictly pinned dependencies and zero ambient shell packages.")
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    """Executes all CI stages sequentially."""
    dry_run = args.dry_run
    results: list[dict[str, Any]] = []

    # 1. Dependency Review
    res_deps = run_dependency_review(dry_run)
    results.append(res_deps)

    # 2. Lint and AST Safety
    lint_py = ROOT_DIR / "tools" / "lint.py"
    results.append(_run_stage("lint-and-ast-safety", [sys.executable, str(lint_py)], dry_run))

    # 3. Schemas Parity
    types_py = ROOT_DIR / "tools" / "generate_types.py"
    results.append(_run_stage("schemas-parity-check", [sys.executable, str(types_py), "--check"], dry_run))

    # 4. Database Migrations Lifecycle
    migrate_py = ROOT_DIR / "tools" / "migrate.py"
    results.append(_run_stage("database-migrations", [sys.executable, str(migrate_py), "--db", ":memory:", "apply"], dry_run))

    # 5. Polyglot Tests
    test_runner_py = ROOT_DIR / "tools" / "test_runner.py"
    results.append(_run_stage("polyglot-tests", [sys.executable, str(test_runner_py), "--all"], dry_run))

    return _process_results("Full CI Pipeline", results, args.json)


def _process_results(pipeline_name: str, results: list[dict[str, Any]], json_mode: bool) -> int:
    """Formats and prints pipeline execution results."""
    all_passed = all(r["exit_code"] == 0 for r in results)
    total_duration = round(sum(r.get("duration_s", 0.0) for r in results), 2)

    if json_mode:
        payload = {
            "pipeline": pipeline_name,
            "all_passed": all_passed,
            "total_duration_s": total_duration,
            "stages": results,
        }
        print(json.dumps(payload, indent=2))
        return 0 if all_passed else 1

    print(f"[*] SYSTEM MIND X — Local CI Pipeline: {pipeline_name}")
    print("-----------------------------------------------------------------")
    print(f"{'Stage':<28} {'Status':<10} {'Duration':<10}")
    print("-----------------------------------------------------------------")

    for r in results:
        duration_str = f"{r.get('duration_s', 0.0):.2f}s"
        print(f"{r['stage']:<28} {r['status']:<10} {duration_str:<10}")

    print("-----------------------------------------------------------------")
    print(f"Total Duration: {total_duration}s | Status: {'PASSED' if all_passed else 'FAILED'}")

    for r in results:
        if r["exit_code"] != 0:
            print(f"\n[!] Failure in stage '{r['stage']}':")
            if "stdout" in r and r["stdout"]:
                print(r["stdout"])
            if "stderr" in r and r["stderr"]:
                print(r["stderr"])
            elif "issues" in r and r["issues"]:
                for issue in r["issues"]:
                    print(f"    - {issue}")

    return 0 if all_passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X Local CI Pipeline Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="top_json",
        help="Emit output in structured JSON format",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="top_dry_run",
        help="Preview stages without running commands",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    for cmd_name, help_text in [
        ("lint", "Run linting, AST safety, secrets scan, and schema parity"),
        ("test", "Run all polyglot tests"),
        ("deps", "Run dependency supply-chain audit"),
        ("all", "Run complete local CI verification pipeline"),
    ]:
        sp = subparsers.add_parser(cmd_name, help=help_text)
        sp.add_argument("--json", action="store_true", dest="sub_json", help="Emit output in JSON format")
        sp.add_argument("--dry-run", action="store_true", dest="sub_dry_run", help="Preview stages without running commands")

    args = parser.parse_args()
    args.dry_run = bool(getattr(args, "top_dry_run", False) or getattr(args, "sub_dry_run", False))
    args.json = bool(getattr(args, "top_json", False) or getattr(args, "sub_json", False))

    commands = {
        "lint": cmd_lint,
        "test": cmd_test,
        "deps": cmd_deps,
        "all": cmd_all,
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
            print(f"[!] Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
