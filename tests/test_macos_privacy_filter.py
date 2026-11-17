"""Unit, contract, and safety test suite for macOS privacy filters, path masking, and metadata sanitization."""

from __future__ import annotations

import ast
import json
from pathlib import Path
import subprocess
import sys
import pytest

from system_mind.macos.privacy_filter import (
    DOC_EXT_REGEX,
    KEY_VAULT_PATTERNS,
    PERSONAL_FOLDERS,
    SECRET_PATTERNS,
    MacPrivacyFilter,
)
from system_mind.macos.privacy_models import (
    PrivacyFilterAuditRecord,
    PrivacyRuleCategory,
    PrivacyScrubbingLevel,
    SanitizedTelemetryEnvelope,
)
from system_mind.packaging.macos_privacy import (
    MacOsPrivacyAuditResult,
    MacOsPrivacyValidator,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = ROOT_DIR / "tools" / "detect_privacy_filter.py"


def test_privacy_models_fidelity() -> None:
    """Verify data models, enums, JSON serialization, and non-negotiable Scan!=Safe invariant."""
    assert PrivacyScrubbingLevel.STRICT.value == "STRICT"
    assert PrivacyScrubbingLevel.BALANCED.value == "BALANCED"
    assert PrivacyScrubbingLevel.MINIMAL.value == "MINIMAL"

    assert PrivacyRuleCategory.USERNAME.value == "USERNAME"
    assert PrivacyRuleCategory.PERSONAL_FOLDER.value == "PERSONAL_FOLDER"
    assert PrivacyRuleCategory.PROTECTED_VAULT.value == "PROTECTED_VAULT"
    assert PrivacyRuleCategory.DOCUMENT_METADATA.value == "DOCUMENT_METADATA"
    assert PrivacyRuleCategory.TOKEN_OR_SECRET.value == "TOKEN_OR_SECRET"

    audit = PrivacyFilterAuditRecord(
        sanitized_usernames_count=3,
        sanitized_paths_count=4,
        sanitized_metadata_count=2,
        redacted_secrets_count=5,
        level=PrivacyScrubbingLevel.BALANCED,
        rules_applied=["RULE_A", "RULE_B"],
        scan_proves_safe=False,
    )

    assert audit.total_redactions == 14
    assert audit.scan_proves_safe is False

    audit_dict = audit.to_dict()
    assert audit_dict["sanitized_usernames_count"] == 3
    assert audit_dict["sanitized_paths_count"] == 4
    assert audit_dict["sanitized_metadata_count"] == 2
    assert audit_dict["redacted_secrets_count"] == 5
    assert audit_dict["total_redactions"] == 14
    assert audit_dict["level"] == "BALANCED"
    assert audit_dict["rules_applied"] == ["RULE_A", "RULE_B"]
    assert audit_dict["scan_proves_safe"] is False

    audit_json = audit.to_json()
    assert '"total_redactions": 14' in audit_json

    env = SanitizedTelemetryEnvelope(
        envelope_id="env-test-01",
        collector_id="fsevents",
        payload={"file": "<PROTECTED_FILE>"},
        audit=audit,
        scan_proves_safe=False,
        is_mock=False,
    )
    env_dict = env.to_dict()
    assert env_dict["envelope_id"] == "env-test-01"
    assert env_dict["collector_id"] == "fsevents"
    assert env_dict["payload"] == {"file": "<PROTECTED_FILE>"}
    assert env_dict["scan_proves_safe"] is False
    assert env_dict["is_mock"] is False

    env_json = env.to_json()
    assert '"envelope_id": "env-test-01"' in env_json


def test_username_pseudonymization_session_stability() -> None:
    """Verify deterministic and consistent pseudonym generation within a session."""
    filter_engine = MacPrivacyFilter(
        level=PrivacyScrubbingLevel.BALANCED,
        salt="test-session-salt-123",
        extra_usernames={"developer_one", "developer_two"},
    )

    pseudo_1a = filter_engine.pseudonymize_username("developer_one")
    pseudo_1b = filter_engine.pseudonymize_username("developer_one")
    pseudo_2 = filter_engine.pseudonymize_username("developer_two")

    assert pseudo_1a == pseudo_1b
    assert pseudo_1a.startswith("user_")
    assert pseudo_2.startswith("user_")
    assert pseudo_1a != pseudo_2

    # Root and daemon should not be pseudonymized
    assert filter_engine.pseudonymize_username("root") == "root"
    assert filter_engine.pseudonymize_username("daemon") == "daemon"


def test_personal_folder_path_masking() -> None:
    """Verify personal folders under /Users/<user>/ are masked under STRICT and BALANCED levels."""
    filter_balanced = MacPrivacyFilter(level=PrivacyScrubbingLevel.BALANCED, extra_usernames={"alice"})

    # Documents
    p1, m1, r1 = filter_balanced.sanitize_path("/Users/alice/Documents/Tax_Return_2025.pdf")
    assert m1 is True
    assert "<PROTECTED_DOCUMENTS>/<REDACTED_DOCUMENT>" in p1
    assert "alice" not in p1

    # Desktop
    p2, m2, _ = filter_balanced.sanitize_path("/Users/alice/Desktop/screenshot.png")
    assert m2 is True
    assert "<PROTECTED_DESKTOP>/<REDACTED_FILE>" in p2

    # Downloads
    p3, m3, _ = filter_balanced.sanitize_path("/Users/alice/Downloads/installer.dmg")
    assert m3 is True
    assert "<PROTECTED_DOWNLOADS>/<REDACTED_DOWNLOAD>" in p3

    # Pictures & Media
    p4, m4, _ = filter_balanced.sanitize_path("/Users/alice/Pictures/vacation.jpg")
    assert m4 is True
    assert "<PROTECTED_PICTURES>/<REDACTED_MEDIA>" in p4

    # Tilde syntax paths
    p5, m5, _ = filter_balanced.sanitize_path("~/Documents/notes.txt")
    assert m5 is True
    assert p5 == "~/<PROTECTED_DOCUMENTS>/<REDACTED_DOCUMENT>"

    p6, m6, _ = filter_balanced.sanitize_path("~/Desktop/work.csv")
    assert m6 is True
    assert p6 == "~/<PROTECTED_DESKTOP>/<REDACTED_FILE>"


def test_key_vault_and_credential_directory_masking() -> None:
    """Verify key vaults, SSH keys, cloud configs, and keychains are masked across all levels."""
    for level in (PrivacyScrubbingLevel.STRICT, PrivacyScrubbingLevel.BALANCED, PrivacyScrubbingLevel.MINIMAL):
        filter_engine = MacPrivacyFilter(level=level, extra_usernames={"bob"})

        # SSH
        p_ssh, m_ssh, r_ssh = filter_engine.sanitize_path("/Users/bob/.ssh/id_rsa")
        assert m_ssh is True
        assert "<PROTECTED_KEY_VAULT>/ssh" in p_ssh

        # AWS
        p_aws, m_aws, _ = filter_engine.sanitize_path("/Users/bob/.aws/credentials")
        assert m_aws is True
        assert "<PROTECTED_KEY_VAULT>/aws" in p_aws

        # GPG
        p_gpg, m_gpg, _ = filter_engine.sanitize_path("/Users/bob/.gnupg/secring.gpg")
        assert m_gpg is True
        assert "<PROTECTED_KEY_VAULT>/gnupg" in p_gpg

        # Keychains
        p_kc, m_kc, _ = filter_engine.sanitize_path("/Users/bob/Library/Keychains/login.keychain")
        assert m_kc is True
        assert "<PROTECTED_KEYCHAINS>" in p_kc

        # Browser profiles
        p_safari, m_saf, _ = filter_engine.sanitize_path("/Users/bob/Library/Safari/Bookmarks.plist")
        assert m_saf is True
        assert "<PROTECTED_BROWSER_DATA>/Safari" in p_safari

        # Tilde vault
        p_t_ssh, m_t_ssh, _ = filter_engine.sanitize_path("~/.ssh/config")
        assert m_t_ssh is True
        assert "<PROTECTED_KEY_VAULT>/ssh" in p_t_ssh


def test_system_paths_preserved() -> None:
    """Verify diagnostic system paths are never altered by privacy filters."""
    filter_engine = MacPrivacyFilter(level=PrivacyScrubbingLevel.STRICT)

    sys_paths = [
        "/System/Library/CoreServices/SystemVersion.plist",
        "/Library/LaunchDaemons/com.apple.sysmond.plist",
        "/Applications/Safari.app/Contents/MacOS/Safari",
        "/usr/bin/sysctl",
        "/usr/sbin/system_profiler",
        "/private/var/log/install.log",
    ]

    for sp in sys_paths:
        cleaned, mod, _ = filter_engine.sanitize_path(sp)
        assert mod is False
        assert cleaned == sp


def test_minimal_level_scope() -> None:
    """Verify MINIMAL level only scrubs credentials, vaults, and secrets, preserving personal doc paths."""
    filter_minimal = MacPrivacyFilter(level=PrivacyScrubbingLevel.MINIMAL, extra_usernames={"carol"})

    # Documents path should retain structure in MINIMAL mode (only username pseudonymized)
    p_doc, m_doc, _ = filter_minimal.sanitize_path("/Users/carol/Documents/budget.xlsx")
    assert "<PROTECTED_DOCUMENTS>" not in p_doc
    assert "/Users/user_" in p_doc

    # Vault should still be masked
    p_ssh, m_ssh, _ = filter_minimal.sanitize_path("/Users/carol/.ssh/id_ed25519")
    assert "<PROTECTED_KEY_VAULT>/ssh" in p_ssh


def test_document_metadata_and_url_query_scrubbing() -> None:
    """Verify window titles and URLs have document filenames and query strings scrubbed."""
    filter_engine = MacPrivacyFilter(level=PrivacyScrubbingLevel.BALANCED)

    # Word document in title
    text1 = "Microsoft Word - Highly_Confidential_Strategy_2026.docx - Editing"
    cleaned1, u1, p1, m1, s1 = filter_engine.sanitize_string(text1)
    assert m1 >= 1
    assert "<REDACTED_DOCUMENT.docx>" in cleaned1
    assert "Highly_Confidential_Strategy_2026" not in cleaned1

    # PDF document
    text2 = "Preview - Q3_Earnings_Report_Draft.pdf"
    cleaned2, _, _, m2, _ = filter_engine.sanitize_string(text2)
    assert m2 >= 1
    assert "<REDACTED_DOCUMENT.pdf>" in cleaned2

    # URL query parameter
    url_text = "Navigated to https://internal.corp/admin/dashboard?auth_token=super_secret_session_token_12345"
    cleaned_url, _, _, m3, _ = filter_engine.sanitize_string(url_text)
    assert m3 >= 1
    assert "<REDACTED_QUERY>" in cleaned_url
    assert "super_secret_session_token_12345" not in cleaned_url


def test_secret_and_token_redaction() -> None:
    """Verify high-entropy keys, bearer tokens, and cloud secrets are redacted."""
    filter_engine = MacPrivacyFilter(level=PrivacyScrubbingLevel.MINIMAL)

    # Bearer token
    t1 = "Authorization: Bearer my_super_secret_jwt_access_token_123456789"
    c1, _, _, _, s1 = filter_engine.sanitize_string(t1)
    assert s1 >= 1
    assert "Bearer <REDACTED_TOKEN>" in c1

    # AWS Access Key
    t2 = "AWS_ACCESS_KEY_ID = AKIAIOSFODNN7EXAMPLE"
    c2, _, _, _, s2 = filter_engine.sanitize_string(t2)
    assert s2 >= 1
    assert "<REDACTED_AWS_KEY>" in c2

    # GitHub token
    t3 = "export GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    c3, _, _, _, s3 = filter_engine.sanitize_string(t3)
    assert s3 >= 1
    assert "<REDACTED_GITHUB_TOKEN>" in c3

    # Generic secret
    t4 = "api_key: 'top_secret_api_key_value_987654321'"
    c4, _, _, _, s4 = filter_engine.sanitize_string(t4)
    assert s4 >= 1
    assert "<REDACTED_SECRET>" in c4


def test_recursive_payload_sanitization() -> None:
    """Verify nested dictionary and list structures are completely sanitized with audit records."""
    filter_engine = MacPrivacyFilter(
        level=PrivacyScrubbingLevel.BALANCED,
        extra_usernames={"dave"},
    )

    nested_payload = {
        "user": {
            "name": "dave",
            "home": "/Users/dave",
        },
        "processes": [
            {
                "pid": 101,
                "command": "/Applications/Xcode.app/Contents/MacOS/Xcode",
                "args": ["/Users/dave/Documents/SecretProject.docx"],
            },
            {
                "pid": 102,
                "command": "ssh",
                "args": ["-i", "/Users/dave/.ssh/id_rsa", "git@github.com"],
                "env": {
                    "TOKEN": "Bearer access_token_secret_abcdef123456",
                },
            },
        ],
    }

    sanitized, audit = filter_engine.sanitize_payload(nested_payload)

    # Check structural integrity
    assert isinstance(sanitized, dict)
    assert sanitized["user"]["name"].startswith("user_")
    assert "/Users/user_" in sanitized["user"]["home"]
    assert "<PROTECTED_DOCUMENTS>" in sanitized["processes"][0]["args"][0]
    assert "<PROTECTED_KEY_VAULT>/ssh" in sanitized["processes"][1]["args"][1]
    assert "Bearer <REDACTED_TOKEN>" in sanitized["processes"][1]["env"]["TOKEN"]

    # Check audit record
    assert audit.sanitized_usernames_count >= 1
    assert audit.sanitized_paths_count >= 2
    assert audit.redacted_secrets_count >= 1
    assert audit.total_redactions >= 4
    assert audit.scan_proves_safe is False
    assert "USERNAME_SANITY" in audit.rules_applied
    assert "PATH_MASKING" in audit.rules_applied
    assert "SECRET_REDACTION" in audit.rules_applied


def test_envelope_sanitization() -> None:
    """Verify envelope wrapping preserves collector ID and enforces scan_proves_safe=False."""
    filter_engine = MacPrivacyFilter(level=PrivacyScrubbingLevel.STRICT, extra_usernames={"emma"})

    raw_env_dict = {
        "collector_id": "fsevents",
        "payload": {
            "file": "/Users/emma/Desktop/confidential.pdf",
        },
        "is_mock": True,
    }

    class DummyEnvelope:
        collector_id = "fsevents"
        payload = {"file": "/Users/emma/Desktop/confidential.pdf"}
        is_mock = True

    sanitized_env = filter_engine.sanitize_envelope(DummyEnvelope())

    assert sanitized_env.collector_id == "fsevents"
    assert sanitized_env.is_mock is True
    assert sanitized_env.scan_proves_safe is False
    assert sanitized_env.audit.scan_proves_safe is False
    assert "<PROTECTED_DESKTOP>" in sanitized_env.payload["file"]


def test_cli_execution_modes() -> None:
    """Verify developer CLI tool executes across --mock, --json, --input, and --level flags."""
    assert CLI_PATH.exists()

    # 1. --mock with table output
    res1 = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res1.returncode == 0
    assert "SYSTEM MIND X — macOS Telemetry Privacy Filter & Sanitization Report" in res1.stdout
    assert "Scan != Safe" in res1.stdout

    # 2. --mock with --json output
    res2 = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--json"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res2.returncode == 0
    data2 = json.loads(res2.stdout)
    assert data2["collector_id"] == "mock_aggregate"
    assert data2["scan_proves_safe"] is False
    assert data2["audit"]["total_redactions"] > 0

    # 3. --input string
    res3 = subprocess.run(
        [
            sys.executable,
            str(CLI_PATH),
            "--input",
            "/Users/frank/.ssh/id_rsa and Bearer secret_token_12345678",
            "--username",
            "frank",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res3.returncode == 0
    data3 = json.loads(res3.stdout)
    assert "<PROTECTED_KEY_VAULT>/ssh" in data3["sanitized"]
    assert "Bearer <REDACTED_TOKEN>" in data3["sanitized"]
    assert data3["audit"]["redacted_secrets_count"] >= 1

    # 4. --level strict
    res4 = subprocess.run(
        [sys.executable, str(CLI_PATH), "--mock", "--level", "strict", "--json"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert res4.returncode == 0
    data4 = json.loads(res4.stdout)
    assert data4["audit"]["level"] == "STRICT"


def test_packaging_validator_audit() -> None:
    """Verify MacOsPrivacyValidator passes with zero issues across all architectural checkpoints."""
    validator = MacOsPrivacyValidator()
    result = validator.audit()

    assert result.valid is True, f"Validator failed with issues: {result.issues}"
    assert len(result.issues) == 0
    assert result.models_valid is True
    assert result.filter_valid is True
    assert result.cli_valid is True
    assert result.sensors_valid is True
    assert result.safety_valid is True


def test_ast_safety_and_zero_ambient_shell() -> None:
    """Verify AST safety invariant SC-01 (no shell=True, no os.system)."""
    target_files = [
        ROOT_DIR / "src" / "system_mind" / "macos" / "privacy_models.py",
        ROOT_DIR / "src" / "system_mind" / "macos" / "privacy_filter.py",
        CLI_PATH,
        ROOT_DIR / "src" / "system_mind" / "packaging" / "macos_privacy.py",
    ]

    for fpath in target_files:
        assert fpath.exists()
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Verify no shell=True
                for kw in node.keywords:
                    if kw.arg == "shell" and isinstance(kw.value, ast.Constant):
                        assert kw.value.value is False, f"Forbidden shell=True at {fpath}:{node.lineno}"

                # Verify no os.system
                if isinstance(node.func, ast.Attribute) and node.func.attr == "system":
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                        pytest.fail(f"Forbidden os.system call at {fpath}:{node.lineno}")
