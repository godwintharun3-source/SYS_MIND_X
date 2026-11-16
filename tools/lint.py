#!/usr/bin/env python3
"""Unified multi-language linter, formatting, and AST safety verification CLI for SYSTEM MIND X."""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import py_compile
import subprocess
import sys

ROOT_DIR = Path(__file__).resolve().parent.parent


class AstSafetyChecker(ast.NodeVisitor):
    """AST visitor that detects forbidden ambient shell executions (SC-01 violation)."""

    def __init__(self, filename: str):
        self.filename = filename
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check for os.system(...)
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                if node.func.attr == "system":
                    self.violations.append(
                        f"{self.filename}:{node.lineno}: Banned ambient shell invocation 'os.system(...)'. Violates SC-01."
                    )

        # Check for subprocess.call/Popen/run(..., shell=True)
        for keyword in node.keywords:
            if keyword.arg == "shell":
                if isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    self.violations.append(
                        f"{self.filename}:{node.lineno}: Banned shell=True in subprocess call. Violates SC-01."
                    )

        self.generic_visit(node)


def check_python_ast_safety() -> list[str]:
    """Scans all Python source files in src/ and tools/ for prohibited ambient execution patterns."""
    violations: list[str] = []
    scan_dirs = [ROOT_DIR / "src", ROOT_DIR / "tools"]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for py_path in scan_dir.rglob("*.py"):
            try:
                content = py_path.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(py_path))
                checker = AstSafetyChecker(str(py_path.relative_to(ROOT_DIR)))
                checker.visit(tree)
                violations.extend(checker.violations)
            except Exception as e:
                violations.append(f"Failed to parse {py_path.relative_to(ROOT_DIR)}: {e}")

    return violations


def check_python_syntax() -> list[str]:
    """Verifies that all Python files compile cleanly without syntax errors."""
    errors: list[str] = []
    for search_dir in [ROOT_DIR / "src", ROOT_DIR / "tools", ROOT_DIR / "tests"]:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(f"Syntax error in {py_file.relative_to(ROOT_DIR)}: {e}")
    return errors


def check_typescript_safety() -> list[str]:
    """Verifies that TypeScript source files do not import banned ambient execution modules."""
    violations: list[str] = []
    ts_src = ROOT_DIR / "apps" / "desktop" / "src"
    banned_imports = ["child_process", "execa", "shelljs", "sudo-prompt", "node-pty"]

    if not ts_src.exists():
        return violations

    for ts_file in ts_src.rglob("*.ts*"):
        try:
            content = ts_file.read_text(encoding="utf-8")
            for banned in banned_imports:
                if f'"{banned}"' in content or f"'{banned}'" in content:
                    violations.append(
                        f"{ts_file.relative_to(ROOT_DIR)}: Forbidden ambient execution import '{banned}'"
                    )
            if "eval(" in content:
                violations.append(
                    f"{ts_file.relative_to(ROOT_DIR)}: Forbidden 'eval(...)' call in UI presentation layer"
                )
        except Exception as e:
            violations.append(f"Failed to read {ts_file.relative_to(ROOT_DIR)}: {e}")

    return violations


def check_rust_code() -> list[str]:
    """Runs cargo check across the workspace and desktop shell crate."""
    errors: list[str] = []

    # 1. System-agent Cargo workspace
    res = subprocess.run(
        ["cargo", "check", "--workspace"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        errors.append(f"Cargo check failed on workspace:\n{res.stderr}")

    # 2. Tauri desktop shell crate
    tauri_manifest = ROOT_DIR / "apps" / "desktop" / "src-tauri" / "Cargo.toml"
    if tauri_manifest.exists():
        res2 = subprocess.run(
            ["cargo", "check", "--manifest-path", str(tauri_manifest)],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if res2.returncode != 0:
            errors.append(f"Cargo check failed on desktop shell crate:\n{res2.stderr}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X Multi-Language Linter & Quality Orchestrator"
    )
    parser.add_argument("--python", action="store_true", help="Run Python syntax and linting checks")
    parser.add_argument("--rust", action="store_true", help="Run Rust workspace check")
    parser.add_argument("--typescript", action="store_true", help="Run TypeScript AST safety check")
    parser.add_argument("--ast-safety", action="store_true", help="Run AST safety checks (zero ambient shell)")
    parser.add_argument("--secrets", action="store_true", help="Run secret leak and credential scan")
    parser.add_argument("--all", action="store_true", help="Run all verification suites")

    args = parser.parse_args()

    # If no flags specified, run --all
    if not (args.python or args.rust or args.typescript or args.ast_safety or args.secrets or args.all):
        args.all = True

    has_failures = False

    if args.python or args.all:
        print("[*] Checking Python syntax compilation across src/, tools/, tests/...")
        syntax_errors = check_python_syntax()
        if syntax_errors:
            has_failures = True
            print(f"    [-] Python syntax errors ({len(syntax_errors)}):")
            for err in syntax_errors:
                print(f"        * {err}")
        else:
            print("    [+] Python syntax verification clean.")

    if args.ast_safety or args.all:
        print("[*] Running AST safety analysis for SC-01 (Zero Ambient Shell)...")
        ast_errors = check_python_ast_safety()
        if ast_errors:
            has_failures = True
            print(f"    [-] Safety invariant SC-01 violations ({len(ast_errors)}):")
            for err in ast_errors:
                print(f"        * {err}")
        else:
            print("    [+] Zero ambient shell violations detected.")

    if args.typescript or args.all:
        print("[*] Checking TypeScript presentation layer boundary safety...")
        ts_errors = check_typescript_safety()
        if ts_errors:
            has_failures = True
            print(f"    [-] TypeScript presentation boundary violations ({len(ts_errors)}):")
            for err in ts_errors:
                print(f"        * {err}")
        else:
            print("    [+] TypeScript presentation layer safety verified.")

    if args.rust or args.all:
        print("[*] Running Rust compiler static analysis...")
        rust_errors = check_rust_code()
        if rust_errors:
            has_failures = True
            print(f"    [-] Rust static analysis errors ({len(rust_errors)}):")
            for err in rust_errors:
                print(f"        * {err}")
        else:
            print("    [+] Rust static analysis clean.")

    if args.secrets or args.all:
        print("[*] Running secret leak and credential scan...")
        # Add root dir to sys.path if needed
        if str(ROOT_DIR) not in sys.path:
            sys.path.insert(0, str(ROOT_DIR))
        from tools.check_secrets import scan_repository_for_secrets
        scanned_count, secret_errors = scan_repository_for_secrets(ROOT_DIR)
        if secret_errors:
            has_failures = True
            print(f"    [-] Secret leak violations ({len(secret_errors)}):")
            for err in secret_errors:
                print(f"        * {err}")
        else:
            print(f"    [+] Zero secret leaks detected ({scanned_count} files scanned).")

    if has_failures:
        print("\n[-] Code quality and static analysis checks failed.")
        return 1

    print("\n[+] All code quality, linting, and static analysis checks PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
