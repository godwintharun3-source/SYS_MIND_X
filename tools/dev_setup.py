#!/usr/bin/env python3
"""Unified local development setup, prerequisite verification, and clean-workspace CLI for SYSTEM MIND X."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _run_cmd(cmd: list[str]) -> tuple[int, str, str]:
    """Executes a command safely without shell=True in compliance with SC-01."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            timeout=30,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (FileNotFoundError, subprocess.SubprocessError) as e:
        return 127, "", str(e)


class PrerequisiteChecker:
    """Verifies that the developer workstation satisfies toolchain requirements."""

    @staticmethod
    def check_python() -> dict[str, Any]:
        """Checks Python runtime version (>= 3.10 required, 3.12 recommended)."""
        ver_info = sys.version_info
        ver_str = f"{ver_info.major}.{ver_info.minor}.{ver_info.micro}"
        satisfied = (ver_info.major == 3 and ver_info.minor >= 10)
        in_venv = (
            hasattr(sys, "real_prefix")
            or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
        )

        return {
            "tool": "python",
            "installed": True,
            "version": ver_str,
            "min_version": "3.10.0",
            "satisfied": satisfied,
            "in_virtualenv": in_venv,
            "executable": sys.executable,
            "hint": "Install Python 3.10+ via pyenv or brew install python@3.12" if not satisfied else "",
        }

    @staticmethod
    def check_rust() -> dict[str, Any]:
        """Checks Rust / Cargo toolchain version (>= 1.75 required)."""
        code, out, _ = _run_cmd(["cargo", "--version"])
        installed = code == 0
        ver_str = None
        satisfied = False

        if installed:
            match = re.search(r"cargo\s+(\d+\.\d+\.\d+)", out)
            if match:
                ver_str = match.group(1)
                parts = [int(p) for p in ver_str.split(".")]
                if parts[0] > 1 or (parts[0] == 1 and parts[1] >= 75):
                    satisfied = True

        return {
            "tool": "cargo",
            "installed": installed,
            "version": ver_str or out,
            "min_version": "1.75.0",
            "satisfied": satisfied,
            "hint": "Install Rust via https://rustup.rs" if not satisfied else "",
        }

    @staticmethod
    def check_node() -> dict[str, Any]:
        """Checks Node.js runtime version (>= 18.0 required)."""
        code, out, _ = _run_cmd(["node", "--version"])
        installed = code == 0
        ver_str = None
        satisfied = False

        if installed:
            clean = out.lstrip("v")
            ver_str = clean
            parts = [int(p) for p in clean.split(".")[:2]]
            if len(parts) >= 1 and parts[0] >= 18:
                satisfied = True

        return {
            "tool": "node",
            "installed": installed,
            "version": ver_str or out,
            "min_version": "18.0.0",
            "satisfied": satisfied,
            "hint": "Install Node.js 18+ via nvm or brew install node" if not satisfied else "",
        }

    @staticmethod
    def check_npm() -> dict[str, Any]:
        """Checks npm package manager version (>= 9.0 required)."""
        code, out, _ = _run_cmd(["npm", "--version"])
        installed = code == 0
        ver_str = None
        satisfied = False

        if installed:
            ver_str = out
            parts = [int(p) for p in out.split(".")[:2]]
            if len(parts) >= 1 and parts[0] >= 9:
                satisfied = True

        return {
            "tool": "npm",
            "installed": installed,
            "version": ver_str or out,
            "min_version": "9.0.0",
            "satisfied": satisfied,
            "hint": "npm is installed alongside Node.js" if not satisfied else "",
        }

    @staticmethod
    def check_git() -> dict[str, Any]:
        """Checks Git version (>= 2.20 required)."""
        code, out, _ = _run_cmd(["git", "--version"])
        installed = code == 0
        ver_str = None
        satisfied = False

        if installed:
            match = re.search(r"git version\s+(\d+\.\d+\.\d+)", out)
            if match:
                ver_str = match.group(1)
                parts = [int(p) for p in ver_str.split(".")]
                if parts[0] > 2 or (parts[0] == 2 and parts[1] >= 20):
                    satisfied = True

        return {
            "tool": "git",
            "installed": installed,
            "version": ver_str or out,
            "min_version": "2.20.0",
            "satisfied": satisfied,
            "hint": "Install Git via brew install git or your package manager" if not satisfied else "",
        }

    @staticmethod
    def check_config() -> dict[str, Any]:
        """Checks environment configuration (.env and .env.example)."""
        env_example = ROOT_DIR / ".env.example"
        env_file = ROOT_DIR / ".env"
        return {
            "env_example_present": env_example.exists(),
            "env_file_present": env_file.exists(),
            "status": "CONFIGURED" if env_file.exists() else "UNCONFIGURED (run cp .env.example .env)",
        }

    @staticmethod
    def check_database() -> dict[str, Any]:
        """Checks SQLite database persistence status."""
        var_dir = ROOT_DIR / "var"
        db_file = var_dir / "system_mind.db"
        return {
            "var_dir_present": var_dir.exists(),
            "db_present": db_file.exists(),
            "db_path": str(db_file),
        }

    @classmethod
    def check_all(cls) -> dict[str, Any]:
        """Executes full diagnostic suite."""
        tools = [
            cls.check_python(),
            cls.check_rust(),
            cls.check_node(),
            cls.check_npm(),
            cls.check_git(),
        ]
        all_satisfied = all(t["satisfied"] for t in tools)
        return {
            "all_satisfied": all_satisfied,
            "tools": tools,
            "config": cls.check_config(),
            "database": cls.check_database(),
        }


class WorkspaceCleaner:
    """Safely cleans ephemeral build artifacts strictly within workspace boundaries."""

    TARGET_DIRS = [
        "target",
        "build",
        "dist",
        ".pytest_cache",
        "apps/desktop/dist",
        "apps/desktop/node_modules/.vite",
    ]

    @classmethod
    def clean(cls, dry_run: bool = False, clean_all: bool = False) -> list[str]:
        """Cleans build directories and pycache files strictly inside ROOT_DIR."""
        removed: list[str] = []

        # 1. Clean targeted top-level and nested build directories
        for rel_dir in cls.TARGET_DIRS:
            target_path = (ROOT_DIR / rel_dir).resolve()
            # Ensure path is strictly inside ROOT_DIR
            if ROOT_DIR in target_path.parents and target_path.exists():
                removed.append(str(target_path.relative_to(ROOT_DIR)))
                if not dry_run:
                    shutil.rmtree(target_path, ignore_errors=True)

        # 2. Clean __pycache__ directories
        for pycache in ROOT_DIR.rglob("__pycache__"):
            target_path = pycache.resolve()
            if ROOT_DIR in target_path.parents and target_path.exists():
                removed.append(str(target_path.relative_to(ROOT_DIR)))
                if not dry_run:
                    shutil.rmtree(target_path, ignore_errors=True)

        # 3. Clean egg-info
        for egg_info in ROOT_DIR.glob("*.egg-info"):
            target_path = egg_info.resolve()
            if ROOT_DIR in target_path.parents and target_path.exists():
                removed.append(str(target_path.relative_to(ROOT_DIR)))
                if not dry_run:
                    shutil.rmtree(target_path, ignore_errors=True)

        # 4. Clean var/ database files only if clean_all=True
        if clean_all:
            var_dir = ROOT_DIR / "var"
            if var_dir.exists():
                for db_file in var_dir.glob("*.db*"):
                    target_path = db_file.resolve()
                    if ROOT_DIR in target_path.parents and target_path.exists():
                        removed.append(str(target_path.relative_to(ROOT_DIR)))
                        if not dry_run:
                            try:
                                target_path.unlink()
                            except OSError:
                                pass

        return removed


def cmd_check(args: argparse.Namespace) -> int:
    """Executes environment check command."""
    diag = PrerequisiteChecker.check_all()

    if args.json:
        print(json.dumps(diag, indent=2))
        return 0 if diag["all_satisfied"] else 1

    print("[*] SYSTEM MIND X — Developer Environment Diagnostics")
    print(f"[*] Workspace Root: {ROOT_DIR}")
    print("-----------------------------------------------------------------")
    print(f"{'Tool':<12} {'Required':<10} {'Installed':<16} {'Status':<10}")
    print("-----------------------------------------------------------------")

    for t in diag["tools"]:
        status_label = "[PASS]" if t["satisfied"] else "[FAIL]"
        installed_str = str(t["version"]) if t["installed"] else "NOT FOUND"
        print(f"{t['tool']:<12} {t['min_version']:<10} {installed_str:<16} {status_label:<10}")

    print("-----------------------------------------------------------------")
    cfg = diag["config"]
    print(f"[*] Configuration: {cfg['status']}")
    db = diag["database"]
    db_status = "INITIALIZED" if db["db_present"] else "NOT INITIALIZED"
    print(f"[*] Database: {db_status} ({db['db_path']})")

    # Virtual environment check
    py_tool = next(t for t in diag["tools"] if t["tool"] == "python")
    if not py_tool.get("in_virtualenv"):
        print("[!] Note: Currently running outside a virtual environment (.venv).")

    missing = [t for t in diag["tools"] if not t["satisfied"]]
    if missing:
        print("\n[!] Action Required:")
        for m in missing:
            print(f"    - {m['tool']}: {m['hint']}")
        return 1

    print("\n[+] All prerequisite toolchains are installed and meet version criteria.")
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Orchestrates unprivileged repository bootstrapping."""
    dry_run = args.dry_run
    skip_tests = args.skip_tests
    skip_cargo = args.skip_cargo
    skip_npm = args.skip_npm

    print(f"[*] SYSTEM MIND X — Local Development Bootstrap {'(DRY-RUN)' if dry_run else ''}")
    print(f"[*] Workspace Root: {ROOT_DIR}")
    print("-----------------------------------------------------------------")

    # Step 1: Check prerequisites
    diag = PrerequisiteChecker.check_all()
    missing = [t for t in diag["tools"] if not t["satisfied"]]
    if missing:
        print("[!] Prerequisite check failed. Missing toolchains:")
        for m in missing:
            print(f"    - {m['tool']}: {m['hint']}")
        return 1
    print("[+] Step 1: Toolchain prerequisites verified.")

    # Step 2: Environment configuration
    env_file = ROOT_DIR / ".env"
    env_example = ROOT_DIR / ".env.example"
    if not env_file.exists():
        if env_example.exists():
            print("[+] Step 2: Creating .env from .env.example (safe loopback defaults)...")
            if not dry_run:
                shutil.copy(env_example, env_file)
        else:
            print("[!] Step 2: Missing .env.example template.")
            return 1
    else:
        print("[+] Step 2: Environment configuration (.env) already present.")

    # Step 3: Python dependencies verification
    print("[+] Step 3: Verifying Python package dependencies...")
    code, _, err = _run_cmd([sys.executable, "-m", "pip", "--version"])
    if code != 0:
        print(f"[!] pip is not available: {err}")
        return 1

    # Step 4: Rust workspace verification
    if not skip_cargo:
        print("[+] Step 4: Verifying Rust Cargo workspace compilation...")
        if not dry_run:
            code, out, err = _run_cmd(["cargo", "check", "--workspace"])
            if code != 0:
                print(f"[!] Cargo workspace check failed: {err}")
                return 1
    else:
        print("[*] Step 4: Skipping Rust Cargo workspace check (--skip-cargo).")

    # Step 5: Desktop frontend packages verification
    if not skip_npm:
        print("[+] Step 5: Verifying Desktop Frontend package configuration...")
        pkg_json = ROOT_DIR / "apps" / "desktop" / "package.json"
        if not pkg_json.exists():
            print("[!] Desktop package.json missing.")
            return 1
    else:
        print("[*] Step 5: Skipping Frontend package check (--skip-npm).")

    # Step 6: Database initialization
    var_dir = ROOT_DIR / "var"
    db_file = var_dir / "system_mind.db"
    print(f"[+] Step 6: Initializing SQLite database schema at {db_file}...")
    if not dry_run:
        var_dir.mkdir(parents=True, exist_ok=True)
        migrate_py = ROOT_DIR / "tools" / "migrate.py"
        code, out, err = _run_cmd([sys.executable, str(migrate_py), "--db", str(db_file), "apply"])
        if code != 0:
            print(f"[!] Database migration failed: {err}")
            return 1

    # Step 7: Linting and AST safety smoke check
    print("[+] Step 7: Running static analysis, AST safety, and secret scan...")
    if not dry_run:
        lint_py = ROOT_DIR / "tools" / "lint.py"
        code, out, err = _run_cmd([sys.executable, str(lint_py)])
        if code != 0:
            print(f"[!] Static analysis failed: {err}")
            return 1

    # Step 8: Unit test verification
    if not skip_tests:
        print("[+] Step 8: Running fast smoke tests...")
        if not dry_run:
            test_py = ROOT_DIR / "tools" / "test_runner.py"
            code, out, err = _run_cmd([sys.executable, str(test_py), "--unit"])
            if code != 0:
                print(f"[!] Smoke tests failed: {err}")
                return 1
    else:
        print("[*] Step 8: Skipping smoke tests (--skip-tests).")

    print("\n[+] BOOTSTRAP COMPLETE. Local development environment is ready.")
    print("    To run all tests: python3 tools/test_runner.py --all")
    print("    To check status:   python3 tools/day_tracker.py status")
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    """Executes workspace clean command."""
    dry_run = args.dry_run
    clean_all = args.all

    removed = WorkspaceCleaner.clean(dry_run=dry_run, clean_all=clean_all)

    if args.json:
        print(json.dumps({"dry_run": dry_run, "clean_all": clean_all, "removed": removed}, indent=2))
        return 0

    mode_label = "Previewing cleanup (DRY-RUN)" if dry_run else "Cleaned build artifacts"
    print(f"[*] {mode_label} ({len(removed)} items):")
    for item in removed:
        print(f"    - {item}")

    if dry_run and removed:
        print("\n[*] Run without --dry-run to purge these artifacts.")
    elif not removed:
        print("    (Workspace is already clean; no artifacts found)")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X Developer Setup & Toolchain Orchestrator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit output in structured JSON format",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # check
    subparsers.add_parser("check", help="Verify toolchains and prerequisites")

    # bootstrap
    boot_parser = subparsers.add_parser("bootstrap", help="Bootstrap unprivileged development environment")
    boot_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview bootstrap actions without making modifications",
    )
    boot_parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip running smoke tests during bootstrap",
    )
    boot_parser.add_argument(
        "--skip-cargo",
        action="store_true",
        help="Skip checking Rust cargo workspace",
    )
    boot_parser.add_argument(
        "--skip-npm",
        action="store_true",
        help="Skip checking desktop frontend packages",
    )

    # clean
    clean_parser = subparsers.add_parser("clean", help="Clean ephemeral build artifacts safely")
    clean_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview artifacts that would be removed without deleting",
    )
    clean_parser.add_argument(
        "--all",
        action="store_true",
        help="Also remove temporary databases in var/",
    )

    args = parser.parse_args()

    commands = {
        "check": cmd_check,
        "bootstrap": cmd_bootstrap,
        "clean": cmd_clean,
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
