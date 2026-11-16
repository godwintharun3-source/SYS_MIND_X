"""Validator for polyglot test framework configurations, marker policies, and orchestrator readiness."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore
from typing import List, Optional


@dataclass(frozen=True)
class TestFrameworkAuditResult:
    """Audit outcome for polyglot test framework configurations and test tiers."""

    __test__ = False
    is_valid: bool
    registered_pytest_markers: List[str]
    missing_pytest_markers: List[str]
    integration_tests_verified: bool
    e2e_tests_verified: bool
    rust_integration_tests_verified: bool
    frontend_test_config_verified: bool
    test_runner_cli_verified: bool
    issues: List[str] = field(default_factory=list)


class TestFrameworkValidator:
    """Enforces presence and completeness of multi-tier test configurations and orchestrator."""

    __test__ = False
    REQUIRED_PYTEST_MARKERS = [
        "unit",
        "integration",
        "e2e",
        "contract",
        "safety_critical",
    ]

    REQUIRED_TEST_FILES = [
        "tests/test_integration_pipeline.py",
        "tests/test_e2e_governance_session.py",
        "crates/system-mind-broker/tests/broker_integration.rs",
        "apps/desktop/vitest.config.ts",
        "apps/desktop/src/__tests__/client.test.ts",
        "tools/test_runner.py",
    ]

    @classmethod
    def audit_test_framework(cls, root_dir: Optional[Path] = None) -> TestFrameworkAuditResult:
        """Audits test configuration files, pytest marker registration, and CLI orchestrator."""
        root = root_dir or Path.cwd()
        issues: List[str] = []
        registered_markers: List[str] = []
        missing_markers: List[str] = []

        # 1. Audit pyproject.toml pytest configuration
        pyproject_path = root / "pyproject.toml"
        if not pyproject_path.exists():
            issues.append("Root pyproject.toml is missing.")
        else:
            try:
                with open(pyproject_path, "rb") as f:
                    pyproj_data = tomllib.load(f)

                pytest_opts = pyproj_data.get("tool", {}).get("pytest", {}).get("ini_options", {})
                raw_markers = pytest_opts.get("markers", [])
                for marker_entry in raw_markers:
                    # Marker format is: "marker_name: description"
                    marker_name = marker_entry.split(":")[0].strip()
                    registered_markers.append(marker_name)

                for req_marker in cls.REQUIRED_PYTEST_MARKERS:
                    if req_marker not in registered_markers:
                        missing_markers.append(req_marker)
                        issues.append(f"Required pytest marker missing from pyproject.toml: '{req_marker}'")

                # Verify strict markers option
                addopts = pytest_opts.get("addopts", "")
                if "--strict-markers" not in addopts:
                    issues.append("pytest addopts must specify '--strict-markers' to prevent untyped marker drift.")

            except Exception as e:
                issues.append(f"Failed to parse pyproject.toml: {e}")

        # 2. Audit existence of required test suite files
        for test_file in cls.REQUIRED_TEST_FILES:
            target = root / test_file
            if not target.exists():
                issues.append(f"Required test framework file missing: '{test_file}'")

        # 3. Check individual tier requirements
        integration_ok = (root / "tests/test_integration_pipeline.py").exists()
        e2e_ok = (root / "tests/test_e2e_governance_session.py").exists()
        rust_ok = (root / "crates/system-mind-broker/tests/broker_integration.rs").exists()
        frontend_ok = (root / "apps/desktop/vitest.config.ts").exists() and (
            root / "apps/desktop/src/__tests__/client.test.ts"
        ).exists()
        runner_path = root / "tools/test_runner.py"
        runner_ok = runner_path.exists() and os.access(runner_path, os.X_OK)

        if not runner_ok and runner_path.exists():
            issues.append("tools/test_runner.py is not marked executable.")

        is_valid = len(issues) == 0

        return TestFrameworkAuditResult(
            is_valid=is_valid,
            registered_pytest_markers=registered_markers,
            missing_pytest_markers=missing_markers,
            integration_tests_verified=integration_ok,
            e2e_tests_verified=e2e_ok,
            rust_integration_tests_verified=rust_ok,
            frontend_test_config_verified=frontend_ok,
            test_runner_cli_verified=runner_ok,
            issues=issues,
        )
