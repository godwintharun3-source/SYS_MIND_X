"""Validator for environment configuration, .env.example templates, and secret-handling conventions."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import List, Optional

from system_mind.config.environment import ConfigLoader, SystemMindConfig


@dataclass(frozen=True)
class EnvironmentConfigAuditResult:
    """Audit outcome for environment configuration and secret-handling conventions."""

    __test__ = False
    is_valid: bool
    has_env_example: bool
    example_variables_count: int
    gitignore_excludes_secrets: bool
    verified_gitignore_patterns: List[str]
    missing_gitignore_patterns: List[str]
    no_committed_secrets: bool
    config_defaults_valid: bool
    issues: List[str] = field(default_factory=list)


class EnvironmentConfigValidator:
    """Enforces presence and completeness of environment templates and secret exclusion rules."""

    __test__ = False

    REQUIRED_EXAMPLE_VARIABLES = [
        "SYSTEM_MIND_ENV",
        "SYSTEM_MIND_HOST",
        "SYSTEM_MIND_PORT",
        "SYSTEM_MIND_IPC_SOCKET",
        "SYSTEM_MIND_LOG_LEVEL",
        "SYSTEM_MIND_SECRET_BACKEND",
        "SYSTEM_MIND_STRICT_INVARIANTS",
        "SYSTEM_MIND_STORAGE_ROOT",
    ]

    REQUIRED_GITIGNORE_SECRET_PATTERNS = [
        ".env",
        ".env.local",
        ".env.*.local",
        "*.pem",
        "*.key",
        "*.pfx",
        "*.p12",
        "id_rsa*",
    ]

    BANNED_TRACKED_FILES = [
        ".env",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
    ]

    @classmethod
    def audit_environment_config(
        cls, root_dir: Optional[Path] = None
    ) -> EnvironmentConfigAuditResult:
        """Audits .env.example, .gitignore secret rules, default configuration validity, and committed secrets."""
        root = root_dir or Path.cwd()
        issues: List[str] = []
        verified_patterns: List[str] = []
        missing_patterns: List[str] = []

        # 1. Check .env.example
        env_example_path = root / ".env.example"
        has_example = env_example_path.exists() and env_example_path.is_file()
        var_count = 0

        if not has_example:
            issues.append("Canonical environment template '.env.example' is missing from repository root.")
        else:
            parsed_example = ConfigLoader.parse_env_file(env_example_path)
            var_count = len(parsed_example)
            for req_var in cls.REQUIRED_EXAMPLE_VARIABLES:
                if req_var not in parsed_example:
                    issues.append(f"Required environment variable missing from .env.example: '{req_var}'")

        # 2. Check .gitignore for secret exclusion patterns
        gitignore_path = root / ".gitignore"
        gitignore_ok = False
        if not gitignore_path.exists():
            issues.append("Root '.gitignore' is missing.")
        else:
            gitignore_text = gitignore_path.read_text(encoding="utf-8")
            gitignore_lines = {line.strip() for line in gitignore_text.splitlines() if line.strip()}
            for pat in cls.REQUIRED_GITIGNORE_SECRET_PATTERNS:
                if pat in gitignore_lines or any(line == pat for line in gitignore_lines):
                    verified_patterns.append(pat)
                else:
                    missing_patterns.append(pat)
                    issues.append(f"Mandatory secret exclusion pattern missing from .gitignore: '{pat}'")
            gitignore_ok = len(missing_patterns) == 0

        # 3. Check for banned plaintext credential files
        no_committed = True
        for banned_file in cls.BANNED_TRACKED_FILES:
            target = root / banned_file
            if target.exists() and target.is_file():
                issues.append(f"Prohibited credential file exists in repository: '{banned_file}'")
                no_committed = False

        # 4. Validate default platform configuration
        defaults_ok = False
        try:
            default_config = SystemMindConfig()
            default_config.validate()
            defaults_ok = True
        except Exception as e:
            issues.append(f"Default SystemMindConfig failed validation: {e}")

        is_valid = len(issues) == 0

        return EnvironmentConfigAuditResult(
            is_valid=is_valid,
            has_env_example=has_example,
            example_variables_count=var_count,
            gitignore_excludes_secrets=gitignore_ok,
            verified_gitignore_patterns=verified_patterns,
            missing_gitignore_patterns=missing_patterns,
            no_committed_secrets=no_committed,
            config_defaults_valid=defaults_ok,
            issues=issues,
        )
