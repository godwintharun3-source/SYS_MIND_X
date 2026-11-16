"""Environment profiles, typed configuration models, and safe config loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any, Dict, Optional

from system_mind.config.secrets import SecretStr


class EnvironmentProfile(str, Enum):
    """Execution deployment environments for SYSTEM MIND X."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"

    @classmethod
    def from_str(cls, value: str) -> EnvironmentProfile:
        val = value.strip().lower()
        for member in cls:
            if member.value == val:
                return member
        raise ValueError(
            f"Invalid environment profile '{value}'. Allowed: {[m.value for m in cls]}"
        )


class SecretStoreBackend(str, Enum):
    """Supported secret storage provider backends."""

    MOCK_MEMORY = "mock_memory"
    ENV_VARS = "env_vars"
    MACOS_KEYCHAIN = "macos_keychain"
    WINDOWS_CREDENTIAL_MANAGER = "windows_credential_manager"
    LINUX_SECRET_SERVICE = "linux_secret_service"

    @classmethod
    def from_str(cls, value: str) -> SecretStoreBackend:
        val = value.strip().lower()
        for member in cls:
            if member.value == val:
                return member
        raise ValueError(
            f"Invalid secret store backend '{value}'. Allowed: {[m.value for m in cls]}"
        )


@dataclass(frozen=True)
class SystemMindConfig:
    """Strongly typed, validated configuration model for the SYSTEM MIND X platform."""

    env: EnvironmentProfile = EnvironmentProfile.DEVELOPMENT
    host: str = "127.0.0.1"
    port: int = 8765
    ipc_socket_path: str = "/tmp/system_mind.sock"
    log_level: str = "INFO"
    secret_backend: SecretStoreBackend = SecretStoreBackend.MOCK_MEMORY
    strict_invariants: bool = True
    storage_root: str = ".system_mind"
    llm_api_key: Optional[SecretStr] = None
    signing_key: Optional[SecretStr] = None
    allow_untrusted_execution: bool = False  # Inviolable: SC-03 ("Scan != Safe")

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Enforces architectural and security invariants on platform configuration."""
        # 1. Port boundaries: Non-privileged user-space port required
        if not (1024 <= self.port <= 65535):
            raise ValueError(
                f"Configuration port {self.port} is outside valid unprivileged range (1024-65535)."
            )

        # 2. Network binding safety: Loopback required by default to prevent ambient exfiltration
        loopback_hosts = {"127.0.0.1", "localhost", "::1"}
        if self.host not in loopback_hosts and self.env != EnvironmentProfile.PRODUCTION:
            raise ValueError(
                f"Host binding '{self.host}' is not a local loopback address. "
                "Development and testing environments must bind exclusively to 127.0.0.1."
            )

        # 3. Log level validity
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Invalid log_level '{self.log_level}'. Allowed: {sorted(valid_log_levels)}"
            )

        # 4. Inviolable Charter Invariants: SC-01 through SC-08
        if not self.strict_invariants:
            raise ValueError(
                "Charter Invariant Violation: 'strict_invariants' cannot be disabled. "
                "All deployment environments mandate active enforcement of SC-01 through SC-08."
            )

        if self.allow_untrusted_execution:
            raise ValueError(
                "Charter Invariant Violation: 'allow_untrusted_execution' cannot be enabled. "
                "SC-03 mandates that unverified or merely scanned payloads must never receive native host execution."
            )

    def as_safe_dict(self) -> Dict[str, Any]:
        """Returns a sanitized dictionary representation with all secrets masked for logging/telemetry."""
        return {
            "env": self.env.value,
            "host": self.host,
            "port": self.port,
            "ipc_socket_path": self.ipc_socket_path,
            "log_level": self.log_level.upper(),
            "secret_backend": self.secret_backend.value,
            "strict_invariants": self.strict_invariants,
            "storage_root": self.storage_root,
            "llm_api_key": str(self.llm_api_key) if self.llm_api_key else None,
            "signing_key": str(self.signing_key) if self.signing_key else None,
            "allow_untrusted_execution": self.allow_untrusted_execution,
        }


class ConfigLoader:
    """Loads and validates configuration from environment variables, .env files, and explicit overrides."""

    ENV_PREFIX = "SYSTEM_MIND_"

    @classmethod
    def parse_env_file(cls, path: Path) -> Dict[str, str]:
        """Parses a key-value .env file safely ignoring comments and blank lines."""
        if not path.exists() or not path.is_file():
            return {}

        env_dict: Dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, val = stripped.split("=", 1)
                clean_key = key.strip()
                clean_val = val.strip()
                # Strip matching surrounding quotes
                if (clean_val.startswith('"') and clean_val.endswith('"')) or (
                    clean_val.startswith("'") and clean_val.endswith("'")
                ):
                    clean_val = clean_val[1:-1]
                env_dict[clean_key] = clean_val

        return env_dict

    @classmethod
    def load(
        cls,
        env_file_path: Optional[Path] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> SystemMindConfig:
        """Loads configuration merging defaults, .env file, OS environment variables, and overrides."""
        merged_raw: Dict[str, Any] = {}

        # 1. Parse .env file if present
        if env_file_path and env_file_path.exists():
            file_values = cls.parse_env_file(env_file_path)
            for k, v in file_values.items():
                if k.startswith(cls.ENV_PREFIX):
                    config_key = k[len(cls.ENV_PREFIX) :].lower()
                    merged_raw[config_key] = v

        # 2. Merge OS environment variables (SYSTEM_MIND_*)
        for k, v in os.environ.items():
            if k.startswith(cls.ENV_PREFIX):
                config_key = k[len(cls.ENV_PREFIX) :].lower()
                merged_raw[config_key] = v

        # 3. Merge explicit overrides
        if overrides:
            for k, v in overrides.items():
                merged_raw[k.lower()] = v

        # 4. Construct typed config
        env_profile = EnvironmentProfile.from_str(
            str(merged_raw.get("env", EnvironmentProfile.DEVELOPMENT.value))
        )
        host = str(merged_raw.get("host", "127.0.0.1"))
        port = int(merged_raw.get("port", 8765))
        ipc_socket = str(merged_raw.get("ipc_socket", merged_raw.get("ipc_socket_path", "/tmp/system_mind.sock")))
        log_level = str(merged_raw.get("log_level", "INFO")).upper()
        secret_backend = SecretStoreBackend.from_str(
            str(merged_raw.get("secret_backend", SecretStoreBackend.MOCK_MEMORY.value))
        )

        strict_inv_raw = merged_raw.get("strict_invariants", True)
        if isinstance(strict_inv_raw, str):
            strict_invariants = strict_inv_raw.lower() in ("true", "1", "yes")
        else:
            strict_invariants = bool(strict_inv_raw)

        storage_root = str(merged_raw.get("storage_root", ".system_mind"))

        # Secrets: Wrap in SecretStr
        raw_llm_key = merged_raw.get("llm_api_key")
        llm_api_key = SecretStr(raw_llm_key) if raw_llm_key else None

        raw_signing_key = merged_raw.get("signing_key")
        signing_key = SecretStr(raw_signing_key) if raw_signing_key else None

        raw_untrusted = merged_raw.get("allow_untrusted_execution", False)
        if isinstance(raw_untrusted, str):
            allow_untrusted = raw_untrusted.lower() in ("true", "1", "yes")
        else:
            allow_untrusted = bool(raw_untrusted)

        return SystemMindConfig(
            env=env_profile,
            host=host,
            port=port,
            ipc_socket_path=ipc_socket,
            log_level=log_level,
            secret_backend=secret_backend,
            strict_invariants=strict_invariants,
            storage_root=storage_root,
            llm_api_key=llm_api_key,
            signing_key=signing_key,
            allow_untrusted_execution=allow_untrusted,
        )
