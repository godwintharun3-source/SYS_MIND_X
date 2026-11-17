"""macOS telemetry privacy filtering engine for path masking, username pseudonymization, and metadata sanitization."""

from __future__ import annotations

import getpass
import hashlib
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from system_mind.macos.privacy_models import (
    PrivacyFilterAuditRecord,
    PrivacyRuleCategory,
    PrivacyScrubbingLevel,
    SanitizedTelemetryEnvelope,
)

# Common personal and sensitive directory names under user home
PERSONAL_FOLDERS = {
    "Documents": "<PROTECTED_DOCUMENTS>/<REDACTED_DOCUMENT>",
    "Desktop": "<PROTECTED_DESKTOP>/<REDACTED_FILE>",
    "Downloads": "<PROTECTED_DOWNLOADS>/<REDACTED_DOWNLOAD>",
    "Pictures": "<PROTECTED_PICTURES>/<REDACTED_MEDIA>",
    "Movies": "<PROTECTED_MOVIES>/<REDACTED_MEDIA>",
    "Music": "<PROTECTED_MUSIC>/<REDACTED_MEDIA>",
}

# Protected cryptographic and cloud credential directories
KEY_VAULT_PATTERNS = [
    (re.compile(r"\.ssh(/.*)?$"), "<PROTECTED_KEY_VAULT>/ssh"),
    (re.compile(r"\.aws(/.*)?$"), "<PROTECTED_KEY_VAULT>/aws"),
    (re.compile(r"\.gnupg(/.*)?$"), "<PROTECTED_KEY_VAULT>/gnupg"),
    (re.compile(r"\.config/gcloud(/.*)?$"), "<PROTECTED_KEY_VAULT>/gcloud"),
    (re.compile(r"\.azure(/.*)?$"), "<PROTECTED_KEY_VAULT>/azure"),
    (re.compile(r"Library/Keychains(/.*)?$"), "<PROTECTED_KEYCHAINS>"),
    (re.compile(r"Library/Safari(/.*)?$"), "<PROTECTED_BROWSER_DATA>/Safari"),
    (re.compile(r"Library/Application Support/Google/Chrome(/.*)?$"), "<PROTECTED_BROWSER_DATA>/Chrome"),
]

# Sensitive token and secret patterns
SECRET_PATTERNS = [
    (re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.\+=/]{8,})['\"]?"), "<REDACTED_SECRET>"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.\+=/]{12,}"), "Bearer <REDACTED_TOKEN>"),
    (re.compile(r"gh[pous]_[A-Za-z0-9_]{36,255}"), "<REDACTED_GITHUB_TOKEN>"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "<REDACTED_AWS_KEY>"),
]

# Sensitive document file pattern (matches document filename + extension in single pass)
DOC_EXT_REGEX = re.compile(
    r"(?i)\b([a-zA-Z0-9_\-\s]+\.(?:keynote|numbers|pages|docx|pptx|xlsx|doc|ppt|xls|odt|rtf|pdf|txt))\b"
)


class MacPrivacyFilter:
    """Deterministic privacy scrubber for paths, usernames, document metadata, and secrets."""

    def __init__(
        self,
        level: PrivacyScrubbingLevel = PrivacyScrubbingLevel.BALANCED,
        salt: str = "system-mind-x-salt",
        extra_usernames: Optional[Set[str]] = None,
    ) -> None:
        self.level = level
        self.salt = salt
        self._pseudonym_cache: Dict[str, str] = {}

        self.known_usernames: Set[str] = set()
        if extra_usernames:
            self.known_usernames.update(extra_usernames)

        # Detect local console user
        try:
            current_user = getpass.getuser()
            if current_user and current_user != "root":
                self.known_usernames.add(current_user)
        except Exception:
            pass

    def pseudonymize_username(self, username: str) -> str:
        """Deterministically map a username to a stable pseudonym without leaking the original name."""
        if username in self._pseudonym_cache:
            return self._pseudonym_cache[username]

        if username == "root" or username == "daemon":
            return username

        h = hashlib.sha256((username + self.salt).encode("utf-8")).hexdigest()[:6]
        pseudo = f"user_{h}"
        self._pseudonym_cache[username] = pseudo
        return pseudo

    def sanitize_path(self, path_str: str) -> Tuple[str, bool, List[str]]:
        """Sanitize paths containing usernames, personal document directories, or key vaults."""
        modified = False
        reasons: List[str] = []
        cleaned = path_str

        # 1. Match and pseudonymize /Users/<user> or /home/<user>
        user_path_match = re.search(r"/(?:Users|home)/([a-zA-Z0-9._-]+)(/.*)?$", cleaned)
        if user_path_match:
            user = user_path_match.group(1)
            rest = user_path_match.group(2) or ""

            if user not in ("Shared", "root", "nobody"):
                self.known_usernames.add(user)
                pseudo = self.pseudonymize_username(user)
                cleaned = re.sub(
                    rf"/(Users|home)/{re.escape(user)}",
                    rf"/\1/{pseudo}",
                    cleaned,
                )
                modified = True
                reasons.append("username_path")

            # Check for key vaults and personal folders in user home
            if rest:
                rest_clean = rest.lstrip("/")
                # Key vaults check
                for pattern, replacement in KEY_VAULT_PATTERNS:
                    if pattern.search(rest_clean):
                        cleaned = re.sub(
                            rf"/(Users|home)/[a-zA-Z0-9._-]+/{pattern.pattern}",
                            rf"/\1/{self.pseudonymize_username(user)}/{replacement}",
                            path_str,
                        )
                        return cleaned, True, ["protected_vault"]

                # Personal folders check
                if self.level in (PrivacyScrubbingLevel.STRICT, PrivacyScrubbingLevel.BALANCED):
                    for folder, replacement in PERSONAL_FOLDERS.items():
                        if rest_clean == folder or rest_clean.startswith(f"{folder}/"):
                            prefix = cleaned.split(f"/{folder}")[0]
                            cleaned = f"{prefix}/{replacement}"
                            return cleaned, True, ["personal_folder"]

        # Check for tilde paths: ~/Documents/...
        if cleaned.startswith("~/"):
            rest_tilde = cleaned[2:]
            for folder, replacement in PERSONAL_FOLDERS.items():
                if rest_tilde == folder or rest_tilde.startswith(f"{folder}/"):
                    cleaned = f"~/{replacement}"
                    return cleaned, True, ["personal_folder"]
            for pattern, replacement in KEY_VAULT_PATTERNS:
                if pattern.search(rest_tilde):
                    cleaned = f"~/{replacement}"
                    return cleaned, True, ["protected_vault"]

        return cleaned, modified, reasons

    def sanitize_string(self, text: str) -> Tuple[str, int, int, int, int]:
        """Sanitize string values for paths, usernames, document titles, and secrets."""
        sanitized_users = 0
        sanitized_paths = 0
        sanitized_meta = 0
        sanitized_secrets = 0
        cleaned = text

        # 1. Scrub secrets and tokens
        for pattern, replacement in SECRET_PATTERNS:
            if pattern.search(cleaned):
                cleaned = pattern.sub(replacement, cleaned)
                sanitized_secrets += 1

        # 2. Scrub paths
        path_matches = re.finditer(r"(?:/(?:Users|home)/[a-zA-Z0-9._/-]+|~/[a-zA-Z0-9._/-]+)", cleaned)
        for m in list(path_matches):
            raw_path = m.group(0)
            clean_path, modified, reasons = self.sanitize_path(raw_path)
            if modified:
                cleaned = cleaned.replace(raw_path, clean_path)
                sanitized_paths += 1
                if "username_path" in reasons:
                    sanitized_users += 1

        # 3. Scrub standalone usernames
        for user in self.known_usernames:
            if user and len(user) >= 3 and user in cleaned:
                # Avoid clobbering common words if username is ambiguous
                pattern = rf"\b{re.escape(user)}\b"
                if re.search(pattern, cleaned):
                    pseudo = self.pseudonymize_username(user)
                    cleaned = re.sub(pattern, pseudo, cleaned)
                    sanitized_users += 1

        # 4. Scrub document titles in window titles or arguments (STRICT or BALANCED)
        if self.level in (PrivacyScrubbingLevel.STRICT, PrivacyScrubbingLevel.BALANCED):
            # Check for document patterns: e.g., "Secret_Project_2026.docx - Word"
            if DOC_EXT_REGEX.search(cleaned):
                def _replace_doc(match: re.Match[str]) -> str:
                    nonlocal sanitized_meta
                    sanitized_meta += 1
                    full = match.group(1)
                    ext = Path(full).suffix.lower()
                    return f"<REDACTED_DOCUMENT{ext}>"

                cleaned = DOC_EXT_REGEX.sub(_replace_doc, cleaned)

            # Strip URL query parameters: ?token=... or ?user=...
            url_match = re.search(r"https?://[^\s]+\?([^\s]+)", cleaned)
            if url_match:
                cleaned = re.sub(r"(\?)[^\s]+", r"\1<REDACTED_QUERY>", cleaned)
                sanitized_meta += 1

        return cleaned, sanitized_users, sanitized_paths, sanitized_meta, sanitized_secrets

    def sanitize_payload(self, data: Any) -> Tuple[Any, PrivacyFilterAuditRecord]:
        """Recursively walk and sanitize any dictionary, list, string, or primitive telemetry payload."""
        total_users = 0
        total_paths = 0
        total_meta = 0
        total_secrets = 0
        rules_applied: Set[str] = set()

        def _traverse(node: Any) -> Any:
            nonlocal total_users, total_paths, total_meta, total_secrets

            if isinstance(node, dict):
                clean_dict = {}
                for k, v in node.items():
                    # Sanitize key if it contains a path or username
                    clean_k, u_k, p_k, m_k, s_k = self.sanitize_string(str(k))
                    clean_v = _traverse(v)
                    clean_dict[clean_k] = clean_v
                return clean_dict

            elif isinstance(node, list):
                return [_traverse(item) for item in node]

            elif isinstance(node, tuple):
                return tuple(_traverse(item) for item in node)

            elif isinstance(node, str):
                cleaned_str, u, p, m, s = self.sanitize_string(node)
                total_users += u
                total_paths += p
                total_meta += m
                total_secrets += s
                if u > 0:
                    rules_applied.add("USERNAME_SANITY")
                if p > 0:
                    rules_applied.add("PATH_MASKING")
                if m > 0:
                    rules_applied.add("DOCUMENT_METADATA_SCRUB")
                if s > 0:
                    rules_applied.add("SECRET_REDACTION")
                return cleaned_str

            return node

        sanitized_data = _traverse(data)

        audit = PrivacyFilterAuditRecord(
            sanitized_usernames_count=total_users,
            sanitized_paths_count=total_paths,
            sanitized_metadata_count=total_meta,
            redacted_secrets_count=total_secrets,
            level=self.level,
            rules_applied=sorted(list(rules_applied)),
            scan_proves_safe=False,  # Enforce non-negotiable charter invariant
        )

        return sanitized_data, audit

    def sanitize_envelope(self, envelope: Any) -> SanitizedTelemetryEnvelope[Any]:
        """Sanitize an ObservedTelemetryEnvelope and wrap in a SanitizedTelemetryEnvelope."""
        raw_payload = envelope.payload if hasattr(envelope, "payload") else envelope
        collector_id = envelope.collector_id if hasattr(envelope, "collector_id") else "unknown"
        is_mock = envelope.is_mock if hasattr(envelope, "is_mock") else False

        clean_payload, audit = self.sanitize_payload(raw_payload)

        env_id = f"sanitized-{collector_id}-{hashlib.sha256(str(clean_payload).encode()).hexdigest()[:8]}"

        return SanitizedTelemetryEnvelope(
            envelope_id=env_id,
            collector_id=collector_id,
            payload=clean_payload,
            audit=audit,
            scan_proves_safe=False,  # Enforce non-negotiable charter invariant
            is_mock=is_mock,
        )
