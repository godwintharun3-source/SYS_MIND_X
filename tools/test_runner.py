#!/usr/bin/env python3
"""Unified polyglot test orchestrator for SYSTEM MIND X.

Orchestrates test execution across all monorepo tiers:
- Python Unit, Integration, and E2E test suites (pytest with markers)
- Rust System-Agent Workspace & Desktop Shell tests (cargo test)
- TypeScript Desktop Frontend tests (Vitest / npm test)

Invariants:
- SC-01: Zero ambient shell execution (shell=False strictly enforced).
- Independent isolation: Each test tier reports status, timing, and failure counts.
- Exit code 0 if and only if all targeted tiers pass.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass
class SuiteResult:
    name: str
    passed: bool
    duration_s: float
    output: str
    return_code: int


class TestOrchestrator:
    """Coordinates execution of multi-tier test suites."""

    def __init__(self, root_dir: Path = ROOT_DIR):
        self.root_dir = root_dir

    def _run_command(self, cmd: list[str], cwd: Path | None = None, env_extra: dict[str, str] | None = None) -> tuple[int, str, float]:
        """Runs a command with shell=False and measures execution duration."""
        env = os.environ.copy()
        if env_extra:
            env.update(env_extra)

        start = time.time()
        try:
            res = subprocess.run(
                cmd,
                cwd=str(cwd or self.root_dir),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            duration = time.time() - start
            output = (res.stdout or "") + ("\n" + res.stderr if res.stderr else "")
            return res.returncode, output.strip(), duration
        except Exception as e:
            duration = time.time() - start
            return 1, str(e), duration

    def run_python_suite(self, marker: str | None = None, name: str = "Python Tests") -> SuiteResult:
        """Executes pytest with optional marker filtering."""
        cmd = [sys.executable, "-m", "pytest", "-v"]
        if marker:
            cmd.extend(["-m", marker])
        cmd.append("tests")

        ret, out, dur = self._run_command(
            cmd,
            env_extra={"PYTHONPATH": "src"},
        )
        return SuiteResult(
            name=name,
            passed=(ret == 0),
            duration_s=dur,
            output=out,
            return_code=ret,
        )

    def run_rust_workspace_tests(self) -> SuiteResult:
        """Executes cargo test across all workspace crates."""
        cmd = ["cargo", "test", "--workspace"]
        ret, out, dur = self._run_command(cmd)
        return SuiteResult(
            name="Rust System-Agent Workspace",
            passed=(ret == 0),
            duration_s=dur,
            output=out,
            return_code=ret,
        )

    def run_rust_desktop_shell_tests(self) -> SuiteResult:
        """Executes cargo test for Tauri desktop presentation shell."""
        cmd = ["cargo", "test", "--manifest-path", "apps/desktop/src-tauri/Cargo.toml"]
        ret, out, dur = self._run_command(cmd)
        return SuiteResult(
            name="Rust Tauri Desktop Shell",
            passed=(ret == 0),
            duration_s=dur,
            output=out,
            return_code=ret,
        )

    def run_frontend_tests(self) -> SuiteResult:
        """Executes desktop frontend unit test suite."""
        desktop_dir = self.root_dir / "apps" / "desktop"
        cmd = ["npm", "test"]
        ret, out, dur = self._run_command(cmd, cwd=desktop_dir)
        return SuiteResult(
            name="Frontend Desktop Scaffold (Vitest)",
            passed=(ret == 0),
            duration_s=dur,
            output=out,
            return_code=ret,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SYSTEM MIND X Unified Test Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--unit", action="store_true", help="Run unit test suites")
    parser.add_argument("--integration", action="store_true", help="Run integration test suites")
    parser.add_argument("--e2e", action="store_true", help="Run end-to-end test suites")
    parser.add_argument("--rust", action="store_true", help="Run Rust workspace and desktop shell tests")
    parser.add_argument("--frontend", action="store_true", help="Run frontend desktop tests")
    parser.add_argument("--all", action="store_true", help="Run all test suites across all languages")
    parser.add_argument("--verbose", "-v", action="store_true", help="Display full test output")

    args = parser.parse_args()

    # Default to --all if no specific flag provided
    run_all = args.all or not (args.unit or args.integration or args.e2e or args.rust or args.frontend)

    orchestrator = TestOrchestrator()
    results: list[SuiteResult] = []

    print("[*] SYSTEM MIND X — Polyglot Test Orchestrator")
    print(f"[*] Target monorepo root: {ROOT_DIR}")
    print("-" * 65)

    if run_all or args.unit:
        print("[*] Running Python Unit tests...")
        results.append(orchestrator.run_python_suite(marker="not integration and not e2e", name="Python Unit Tests"))

    if run_all or args.integration:
        print("[*] Running Python Integration tests...")
        results.append(orchestrator.run_python_suite(marker="integration", name="Python Integration Tests"))

    if run_all or args.e2e:
        print("[*] Running Python E2E tests...")
        results.append(orchestrator.run_python_suite(marker="e2e", name="Python E2E Tests"))

    if run_all or args.rust:
        print("[*] Running Rust System-Agent Workspace tests...")
        results.append(orchestrator.run_rust_workspace_tests())
        print("[*] Running Rust Tauri Desktop Shell tests...")
        results.append(orchestrator.run_rust_desktop_shell_tests())

    if run_all or args.frontend:
        print("[*] Running Frontend Desktop Scaffold tests...")
        results.append(orchestrator.run_frontend_tests())

    print("\n" + "=" * 65)
    print(f"{'Test Suite':<40} | {'Status':<8} | {'Duration':<8}")
    print("=" * 65)

    all_passed = True
    for res in results:
        status_str = "PASSED" if res.passed else "FAILED"
        if not res.passed:
            all_passed = False
        print(f"{res.name:<40} | {status_str:<8} | {res.duration_s:6.2f}s")
        if args.verbose or not res.passed:
            print("\n--- Output for " + res.name + " ---")
            print(res.output)
            print("-" * 40)

    print("=" * 65)
    total_duration = sum(r.duration_s for r in results)
    print(f"Total Suites: {len(results)} | Duration: {total_duration:.2f}s")

    if all_passed:
        print("\n[+] ALL TEST SUITES PASSED CLEANLY.")
        return 0
    else:
        print("\n[!] ONE OR MORE TEST SUITES FAILED.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
