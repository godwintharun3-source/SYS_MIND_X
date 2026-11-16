"""Validator enforcing strict dependency pinning, entrypoint contracts, and package metadata."""

from __future__ import annotations

from pathlib import Path
import re
import tomllib
from typing import Any, Dict, List, Optional

import system_mind
from system_mind.packaging.models import PackageMetadata, PackageVerificationResult


class PackageConfigValidator:
    """Validates pyproject.toml compliance, security constraints, and deterministic pinning."""

    EXPECTED_PACKAGE_NAME = "system-mind-backend"
    EXPECTED_PYTHON_REQUIREMENT = ">=3.10"
    EXPECTED_CLI_ENTRYPOINT = "system_mind.cli:main"

    PROHIBITED_PACKAGES = {
        "sh",
        "plumbum",
        "subprocess32",
        "shellingham",
        "pexpect",
        "fabric",
    }

    @classmethod
    def load_pyproject(cls, pyproject_path: Optional[Path] = None) -> Dict[str, Any]:
        """Parse pyproject.toml using standard tomllib."""
        path = pyproject_path or Path.cwd() / "pyproject.toml"
        if not path.exists():
            raise FileNotFoundError(f"pyproject.toml not found at: {path}")

        with open(path, "rb") as f:
            return tomllib.load(f)

    @classmethod
    def extract_metadata(cls, data: Dict[str, Any]) -> PackageMetadata:
        """Extract typed metadata from parsed pyproject.toml."""
        project = data.get("project", {})
        optional_deps = project.get("optional-dependencies", {})
        dev_deps = optional_deps.get("dev", [])

        return PackageMetadata(
            name=project.get("name", ""),
            version=project.get("version", ""),
            requires_python=project.get("requires-python", ""),
            scripts=project.get("scripts", {}),
            dependencies=project.get("dependencies", []),
            dev_dependencies=dev_deps,
        )

    @classmethod
    def validate(cls, pyproject_path: Optional[Path] = None) -> PackageVerificationResult:
        """Execute full compliance audit on package metadata and dependencies."""
        data = cls.load_pyproject(pyproject_path)
        meta = cls.extract_metadata(data)

        issues: List[str] = []
        unpinned: List[str] = []
        prohibited: List[str] = []

        # 1. Name compliance
        if meta.name != cls.EXPECTED_PACKAGE_NAME:
            issues.append(
                f"Invalid package name '{meta.name}'. Expected '{cls.EXPECTED_PACKAGE_NAME}'."
            )

        # 2. Version sync with package __version__
        if meta.version != system_mind.__version__:
            issues.append(
                f"Version desynchronization: pyproject.toml defines '{meta.version}', "
                f"but system_mind.__version__ is '{system_mind.__version__}'."
            )

        # 3. Python version requirement
        if meta.requires_python != cls.EXPECTED_PYTHON_REQUIREMENT:
            issues.append(
                f"Invalid requires-python '{meta.requires_python}'. Expected '{cls.EXPECTED_PYTHON_REQUIREMENT}'."
            )

        # 4. CLI Entrypoint validation
        entrypoint = meta.scripts.get("system-mind")
        entrypoint_valid = entrypoint == cls.EXPECTED_CLI_ENTRYPOINT
        if not entrypoint_valid:
            issues.append(
                f"Missing or invalid CLI entrypoint: 'system-mind' -> '{entrypoint}'. "
                f"Expected '{cls.EXPECTED_CLI_ENTRYPOINT}'."
            )

        # 5. Dependency Pinning & Prohibited package scans
        all_deps = meta.dependencies + meta.dev_dependencies
        pin_regex = re.compile(r"^([a-zA-Z0-9_\-]+)==([a-zA-Z0-9_.\-]+)$")

        for dep in all_deps:
            match = pin_regex.match(dep.strip())
            if not match:
                unpinned.append(dep)
                issues.append(f"Unpinned dependency detected: '{dep}'. Exact '==' pinning is mandated.")
                pkg_name = dep.split(">=")[0].split("<=")[0].split("==")[0].strip()
            else:
                pkg_name = match.group(1).lower()

            if pkg_name in cls.PROHIBITED_PACKAGES:
                prohibited.append(pkg_name)
                issues.append(
                    f"Prohibited package detected: '{pkg_name}'. Ambient execution packages are banned."
                )

        # 6. Pytest tool configuration check
        pytest_cfg = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
        if "tests" not in pytest_cfg.get("testpaths", []):
            issues.append("pytest tool configuration missing 'tests' in testpaths.")
        if "src" not in pytest_cfg.get("pythonpath", []):
            issues.append("pytest tool configuration missing 'src' in pythonpath.")

        is_valid = len(issues) == 0

        return PackageVerificationResult(
            is_valid=is_valid,
            name=meta.name,
            version=meta.version,
            requires_python=meta.requires_python,
            entrypoint_valid=entrypoint_valid,
            unpinned_dependencies=unpinned,
            prohibited_dependencies=prohibited,
            issues=issues,
        )
