"""Unit and contract tests for environment configuration, secret masking, and leak detection."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import pytest

from system_mind.config import (
    ConfigLoader,
    EnvironmentProfile,
    MockMemorySecretStore,
    SecretLeakDetector,
    SecretStoreBackend,
    SecretStr,
    SystemMindConfig,
)
from system_mind.packaging import (
    EnvironmentConfigAuditResult,
    EnvironmentConfigValidator,
)


def test_system_mind_config_defaults_and_validation():
    """Verify default configuration parameters and safe dictionary export."""
    cfg = SystemMindConfig()

    assert cfg.env == EnvironmentProfile.DEVELOPMENT
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.ipc_socket_path == "/tmp/system_mind.sock"
    assert cfg.log_level == "INFO"
    assert cfg.secret_backend == SecretStoreBackend.MOCK_MEMORY
    assert cfg.strict_invariants is True
    assert cfg.allow_untrusted_execution is False

    safe_dict = cfg.as_safe_dict()
    assert safe_dict["host"] == "127.0.0.1"
    assert safe_dict["port"] == 8765
    assert safe_dict["strict_invariants"] is True
    assert safe_dict["allow_untrusted_execution"] is False


def test_system_mind_config_security_invariants():
    """Verify that insecure ports, non-loopback hosts, and invariant waivers raise ValueError."""
    # 1. Privileged port rejection
    with pytest.raises(ValueError, match="outside valid unprivileged range"):
        SystemMindConfig(port=80)

    # 2. Port overflow rejection
    with pytest.raises(ValueError, match="outside valid unprivileged range"):
        SystemMindConfig(port=70000)

    # 3. Non-loopback host in development rejection
    with pytest.raises(ValueError, match="not a local loopback address"):
        SystemMindConfig(host="0.0.0.0")

    # 4. Strict invariants waiver rejection
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        SystemMindConfig(strict_invariants=False)

    # 5. Untrusted execution waiver rejection (SC-03)
    with pytest.raises(ValueError, match="Charter Invariant Violation"):
        SystemMindConfig(allow_untrusted_execution=True)


def test_config_loader_from_env_file_and_overrides():
    """Verify parsing of .env files and merging with explicit overrides."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        env_file = Path(tmp_dir) / ".env"
        env_content = """
# System Mind local config
SYSTEM_MIND_ENV=testing
SYSTEM_MIND_PORT=9999
SYSTEM_MIND_LOG_LEVEL=DEBUG
SYSTEM_MIND_LLM_API_KEY="test_mock_api_key_123"
SYSTEM_MIND_SIGNING_KEY='test_signing_key_456'
"""
        env_file.write_text(env_content)

        cfg = ConfigLoader.load(env_file_path=env_file)
        assert cfg.env == EnvironmentProfile.TESTING
        assert cfg.port == 9999
        assert cfg.log_level == "DEBUG"
        assert cfg.llm_api_key is not None
        assert isinstance(cfg.llm_api_key, SecretStr)
        assert cfg.llm_api_key.get_secret_value() == "test_mock_api_key_123"

        # Safe dict masks the keys
        safe_dict = cfg.as_safe_dict()
        assert safe_dict["llm_api_key"] == "***REDACTED***"
        assert safe_dict["signing_key"] == "***REDACTED***"


def test_secret_str_masking_and_unmasking():
    """Verify SecretStr completely masks raw strings in formatting, repr, and str."""
    raw = "ghp_SECRET_TOKEN_DO_NOT_LEAK_9999"
    secret = SecretStr(raw)

    # Must be masked
    assert str(secret) == "***REDACTED***"
    assert repr(secret) == "SecretStr('***REDACTED***')"
    assert f"Authorization: {secret}" == "Authorization: ***REDACTED***"
    assert raw not in str(secret)
    assert raw not in repr(secret)

    # Raw value accessible only through explicit method
    assert secret.get_secret_value() == raw
    assert len(secret) == len(raw)

    # Deterministic fingerprint for audit tracking without leaking token
    fp1 = secret.hash_fingerprint()
    fp2 = SecretStr(raw).hash_fingerprint()
    fp3 = SecretStr("other_token").hash_fingerprint()
    assert fp1 == fp2
    assert fp1 != fp3
    assert len(fp1) == 64


def test_mock_memory_secret_store():
    """Verify in-memory secret store operations and type checking."""
    store = MockMemorySecretStore()
    token = SecretStr("secret_db_pass_123")

    store.store_secret("db_pass", token)
    assert store.has_secret("db_pass") is True
    assert store.has_secret("missing") is False

    retrieved = store.get_secret("db_pass")
    assert retrieved is not None
    assert retrieved.get_secret_value() == "secret_db_pass_123"

    assert store.delete_secret("db_pass") is True
    assert store.delete_secret("db_pass") is False
    assert store.has_secret("db_pass") is False

    # Type safety
    with pytest.raises(TypeError):
        store.store_secret("bad", "plain_string_not_allowed")  # type: ignore


def test_secret_leak_detector_catches_patterns():
    """Verify pattern-based detection of API keys and private keys."""
    # 1. Private key header
    pem_text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA..."
    findings_pem = SecretLeakDetector.detect_secrets_in_text(pem_text)
    assert len(findings_pem) > 0
    assert any("PRIVATE_KEY_HEADER" in f for f in findings_pem)

    # 2. GitHub token
    gh_text = "Bearer ghp_111122223333444455556666777788889999"
    findings_gh = SecretLeakDetector.detect_secrets_in_text(gh_text)
    assert len(findings_gh) > 0
    assert any("GITHUB_TOKEN" in f for f in findings_gh)

    # 3. Clean text has no findings
    clean_text = "This is a clean developer documentation string."
    assert SecretLeakDetector.detect_secrets_in_text(clean_text) == []

    # 4. Dictionary inspection flags unmasked credentials
    nested_data = {
        "user": "developer",
        "api_key": "unmasked_raw_secret_value",
        "nested": {"token": "ghp_111122223333444455556666777788889999"},
    }
    findings_dict = SecretLeakDetector.detect_secrets_in_dict(nested_data)
    assert len(findings_dict) >= 2


def test_environment_config_validator_audits_clean():
    """Verify that current repository passes the EnvironmentConfigValidator audit."""
    result = EnvironmentConfigValidator.audit_environment_config()

    assert result.is_valid is True
    assert len(result.issues) == 0
    assert result.has_env_example is True
    assert result.example_variables_count >= 8
    assert result.gitignore_excludes_secrets is True
    assert result.missing_gitignore_patterns == []
    assert result.no_committed_secrets is True
    assert result.config_defaults_valid is True


def test_environment_config_validator_detects_violations():
    """Verify validator flags missing templates or missing gitignore patterns."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Incomplete .env.example
        (tmp_path / ".env.example").write_text("SYSTEM_MIND_ENV=development\n")

        # Incomplete .gitignore
        (tmp_path / ".gitignore").write_text(".venv\n")

        result = EnvironmentConfigValidator.audit_environment_config(tmp_path)
        assert result.is_valid is False
        assert result.gitignore_excludes_secrets is False
        assert ".env" in result.missing_gitignore_patterns
        assert any("SYSTEM_MIND_HOST" in issue for issue in result.issues)


def test_check_secrets_cli():
    """Verify that tools/check_secrets.py runs cleanly against the repository."""
    root_dir = Path(__file__).resolve().parent.parent
    cli_path = root_dir / "tools" / "check_secrets.py"

    res = subprocess.run(
        [sys.executable, str(cli_path)],
        cwd=str(root_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "Zero secret leaks detected" in res.stdout
