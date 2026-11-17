"""Read-only macOS application signature and Gatekeeper notarization inspector."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from pathlib import Path
import platform
import subprocess
from typing import Any, Dict, List, Optional, Set

from system_mind.macos.signature_models import (
    MacAppSignatureInfo,
    MacAppSignatureReport,
    NotarizationStatus,
    SignatureStatus,
    SigningAuthorityType,
)

logger = logging.getLogger(__name__)


class MacAppSignatureDetector:
    """Read-only, passive introspection engine for macOS application signatures and notarization."""

    CODESIGN_PATH = Path("/usr/bin/codesign")
    SPCTL_PATH = Path("/usr/sbin/spctl")

    DEFAULT_INSPECTION_PATHS: List[Path] = [
        Path("/System/Applications/Safari.app"),
        Path("/System/Applications/Calculator.app"),
        Path("/System/Applications/Utilities/Terminal.app"),
        Path("/System/Applications/TextEdit.app"),
        Path("/Applications/Safari.app"),
    ]

    def __init__(
        self,
        codesign_path: Optional[Path] = None,
        spctl_path: Optional[Path] = None,
    ) -> None:
        self.codesign_path = codesign_path or self.CODESIGN_PATH
        self.spctl_path = spctl_path or self.SPCTL_PATH

    def parse_codesign_details(
        self,
        stderr_output: str,
        stdout_output: str = "",
    ) -> Dict[str, Any]:
        """Parse raw key-value output from `codesign -dv --verbose=4`."""
        combined = f"{stdout_output}\n{stderr_output}"
        details: Dict[str, Any] = {
            "executable_path": None,
            "bundle_id": None,
            "format": None,
            "authorities": [],
            "team_id": None,
            "cdhash": None,
            "is_hardened_runtime": False,
            "is_adhoc": False,
            "is_unsigned": False,
        }

        # Check for unsigned binary markers
        lower_output = combined.lower()
        if "code object is not signed at all" in lower_output:
            details["is_unsigned"] = True
            return details

        for line in combined.splitlines():
            line_str = line.strip()
            if not line_str:
                continue

            if line_str.startswith("Executable="):
                details["executable_path"] = line_str.split("=", 1)[1].strip()
            elif line_str.startswith("Identifier="):
                details["bundle_id"] = line_str.split("=", 1)[1].strip()
            elif line_str.startswith("Format="):
                details["format"] = line_str.split("=", 1)[1].strip()
            elif line_str.startswith("Authority="):
                auth_val = line_str.split("=", 1)[1].strip()
                if auth_val:
                    details["authorities"].append(auth_val)
            elif line_str.startswith("TeamIdentifier="):
                team_val = line_str.split("=", 1)[1].strip()
                if team_val and team_val.lower() != "not set":
                    details["team_id"] = team_val
            elif line_str.startswith("CDHash="):
                details["cdhash"] = line_str.split("=", 1)[1].strip()
            elif line_str.startswith("CodeDirectory"):
                # Detect hardened runtime flag
                if "runtime" in line_str.lower() or "0x10000" in line_str:
                    details["is_hardened_runtime"] = True
            elif line_str.startswith("Signature="):
                sig_val = line_str.split("=", 1)[1].strip()
                if sig_val.lower() == "adhoc":
                    details["is_adhoc"] = True

        if not details["authorities"] and not details["is_unsigned"] and details["is_adhoc"]:
            details["is_adhoc"] = True

        return details

    def parse_spctl_assessment(
        self,
        stdout_output: str,
        stderr_output: str,
        returncode: int,
    ) -> NotarizationStatus:
        """Parse Gatekeeper assessment output from `spctl --assess --type execute --verbose`."""
        combined = f"{stdout_output}\n{stderr_output}".lower()

        if "source=apple system" in combined:
            return NotarizationStatus.APPLE_SYSTEM
        elif "source=notarized developer id" in combined:
            return NotarizationStatus.NOTARIZED_DEVELOPER_ID
        elif "source=mac app store" in combined:
            return NotarizationStatus.MAC_APP_STORE
        elif "rejected" in combined or returncode != 0:
            if "no usable signature" in combined or "code object is not signed" in combined:
                return NotarizationStatus.NOT_APPLICABLE
            return NotarizationStatus.REJECTED
        elif "accepted" in combined:
            return NotarizationStatus.NOTARIZED_DEVELOPER_ID

        return NotarizationStatus.UNKNOWN

    def classify_signing_authority(
        self,
        authorities: List[str],
        is_adhoc: bool,
        is_unsigned: bool,
    ) -> tuple[SigningAuthorityType, bool]:
        """Classify primary signing authority type and whether binary is signed by Apple Inc."""
        if is_unsigned:
            return SigningAuthorityType.UNSIGNED, False

        if is_adhoc or (not authorities and is_adhoc):
            return SigningAuthorityType.ADHOC, False

        for auth in authorities:
            auth_lower = auth.lower()
            if "software signing" in auth_lower or "apple system" in auth_lower:
                return SigningAuthorityType.APPLE_SYSTEM, True
            if "apple mac os application signing" in auth_lower or "mac app store" in auth_lower:
                return SigningAuthorityType.APP_STORE, True
            if "developer id application" in auth_lower:
                return SigningAuthorityType.DEVELOPER_ID, False

        # Check for generic Apple Root CA anchor
        if authorities:
            is_apple = bool(authorities) and any(
                x in authorities[0].lower()
                for x in ("apple inc.", "apple software", "macos software", "apple system")
            )
            return SigningAuthorityType.THIRD_PARTY_CA, is_apple

        return SigningAuthorityType.UNKNOWN, False

    def verify_strict_signature(self, path: Path) -> bool:
        """Execute strict cryptographic seal verification using `codesign -v --strict <path>`."""
        if not self.codesign_path.exists() or platform.system() != "Darwin":
            return False

        try:
            cmd = [str(self.codesign_path), "-v", "--strict", str(path)]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return res.returncode == 0
        except (subprocess.TimeoutExpired, PermissionError, OSError) as exc:
            logger.debug(f"Strict codesign check failed for {path}: {exc}")
            return False

    def assess_gatekeeper(self, path: Path) -> NotarizationStatus:
        """Assess Gatekeeper notarization status using `spctl --assess --type execute --verbose <path>`."""
        if not self.spctl_path.exists() or platform.system() != "Darwin":
            return NotarizationStatus.UNKNOWN

        try:
            cmd = [
                str(self.spctl_path),
                "--assess",
                "--type",
                "execute",
                "--verbose",
                str(path),
            ]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return self.parse_spctl_assessment(res.stdout, res.stderr, res.returncode)
        except (subprocess.TimeoutExpired, PermissionError, OSError) as exc:
            logger.debug(f"spctl assessment failed for {path}: {exc}")
            return NotarizationStatus.UNKNOWN

    def inspect_bundle(self, bundle_path: Path | str) -> MacAppSignatureInfo:
        """Inspect a single application bundle or binary for signatures and notarization."""
        path = Path(bundle_path).resolve()
        path_str = str(path)
        bundle_id = path.stem

        if not path.exists():
            return MacAppSignatureInfo(
                bundle_id=bundle_id,
                bundle_path=path_str,
                signature_status=SignatureStatus.UNKNOWN,
                notarization_status=NotarizationStatus.UNKNOWN,
                authority_type=SigningAuthorityType.UNKNOWN,
                scan_proves_safe=False,
            )

        if platform.system() != "Darwin" or not self.codesign_path.exists():
            # Graceful non-Darwin fallback
            return MacAppSignatureInfo(
                bundle_id=bundle_id,
                bundle_path=path_str,
                signature_status=SignatureStatus.UNKNOWN,
                notarization_status=NotarizationStatus.UNKNOWN,
                authority_type=SigningAuthorityType.UNKNOWN,
                scan_proves_safe=False,
            )

        # 1. Query detailed codesign properties
        raw_stderr = ""
        raw_stdout = ""
        try:
            cmd = [str(self.codesign_path), "-dv", "--verbose=4", str(path)]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            raw_stdout = res.stdout
            raw_stderr = res.stderr
        except (subprocess.TimeoutExpired, PermissionError, OSError) as exc:
            logger.debug(f"codesign invocation failed for {path}: {exc}")

        details = self.parse_codesign_details(raw_stderr, raw_stdout)

        parsed_bundle_id = details["bundle_id"] or bundle_id
        is_unsigned = details["is_unsigned"]
        is_adhoc = details["is_adhoc"]
        authorities = details["authorities"]

        authority_type, is_apple = self.classify_signing_authority(
            authorities=authorities,
            is_adhoc=is_adhoc,
            is_unsigned=is_unsigned,
        )

        # 2. Strict cryptographic integrity verification
        if is_unsigned:
            is_valid = False
            sig_status = SignatureStatus.UNSIGNED
            notarization_status = NotarizationStatus.NOT_APPLICABLE
        elif is_adhoc:
            is_valid = self.verify_strict_signature(path)
            sig_status = SignatureStatus.ADHOC_SIGNED
            notarization_status = NotarizationStatus.NOT_APPLICABLE
        else:
            is_valid = self.verify_strict_signature(path)
            sig_status = SignatureStatus.SIGNED_VALID if is_valid else SignatureStatus.SIGNED_INVALID
            # 3. Gatekeeper notarization assessment
            notarization_status = self.assess_gatekeeper(path)
            if notarization_status == NotarizationStatus.UNKNOWN:
                if authority_type == SigningAuthorityType.APPLE_SYSTEM:
                    notarization_status = NotarizationStatus.APPLE_SYSTEM
                elif authority_type == SigningAuthorityType.APP_STORE:
                    notarization_status = NotarizationStatus.MAC_APP_STORE

        return MacAppSignatureInfo(
            bundle_id=parsed_bundle_id,
            bundle_path=path_str,
            executable_path=details["executable_path"],
            signature_status=sig_status,
            notarization_status=notarization_status,
            authority_type=authority_type,
            authorities=authorities,
            team_id=details["team_id"],
            cdhash=details["cdhash"],
            is_hardened_runtime=details["is_hardened_runtime"],
            is_apple=is_apple,
            is_valid=is_valid,
            scan_proves_safe=False,  # Enforce Charter Invariant: Scan != Safe
        )

    def inspect_app(self, app_path: Path | str) -> MacAppSignatureInfo:
        """Alias for inspect_bundle for inspecting a single application bundle or binary."""
        return self.inspect_bundle(app_path)

    def detect_mock(self) -> MacAppSignatureReport:
        """Construct deterministic Apple Silicon application signature mock."""
        signatures: List[MacAppSignatureInfo] = [
            MacAppSignatureInfo(
                bundle_id="com.apple.Safari",
                bundle_path="/System/Applications/Safari.app",
                executable_path="/System/Applications/Safari.app/Contents/MacOS/Safari",
                signature_status=SignatureStatus.SIGNED_VALID,
                notarization_status=NotarizationStatus.APPLE_SYSTEM,
                authority_type=SigningAuthorityType.APPLE_SYSTEM,
                authorities=[
                    "macOS Software Signing",
                    "Apple Code Signing Certification Authority",
                    "Apple Root CA",
                ],
                team_id=None,
                cdhash="9a35f082e6ef22e8316e6d117a52f4aa5b8c9d01",
                is_hardened_runtime=True,
                is_apple=True,
                is_valid=True,
                scan_proves_safe=False,
            ),
            MacAppSignatureInfo(
                bundle_id="com.apple.calculator",
                bundle_path="/System/Applications/Calculator.app",
                executable_path="/System/Applications/Calculator.app/Contents/MacOS/Calculator",
                signature_status=SignatureStatus.SIGNED_VALID,
                notarization_status=NotarizationStatus.APPLE_SYSTEM,
                authority_type=SigningAuthorityType.APPLE_SYSTEM,
                authorities=[
                    "macOS Software Signing",
                    "Apple Code Signing Certification Authority",
                    "Apple Root CA",
                ],
                team_id=None,
                cdhash="009e99aa1b37ebade67c8914e13c2e9946ca24ef",
                is_hardened_runtime=False,
                is_apple=True,
                is_valid=True,
                scan_proves_safe=False,
            ),
            MacAppSignatureInfo(
                bundle_id="com.microsoft.VSCode",
                bundle_path="/Applications/Visual Studio Code.app",
                executable_path="/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
                signature_status=SignatureStatus.SIGNED_VALID,
                notarization_status=NotarizationStatus.NOTARIZED_DEVELOPER_ID,
                authority_type=SigningAuthorityType.DEVELOPER_ID,
                authorities=[
                    "Developer ID Application: Microsoft Corporation (UBF8T346G9)",
                    "Developer ID Certification Authority",
                    "Apple Root CA",
                ],
                team_id="UBF8T346G9",
                cdhash="3d21b7c093a1c8438b4382f719329bc0428e5792",
                is_hardened_runtime=True,
                is_apple=False,
                is_valid=True,
                scan_proves_safe=False,
            ),
            MacAppSignatureInfo(
                bundle_id="com.google.Chrome",
                bundle_path="/Applications/Google Chrome.app",
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                signature_status=SignatureStatus.SIGNED_VALID,
                notarization_status=NotarizationStatus.NOTARIZED_DEVELOPER_ID,
                authority_type=SigningAuthorityType.DEVELOPER_ID,
                authorities=[
                    "Developer ID Application: Google LLC (EQHXZ8M8AV)",
                    "Developer ID Certification Authority",
                    "Apple Root CA",
                ],
                team_id="EQHXZ8M8AV",
                cdhash="82bf24ca70e932314a72d32baefc200e129ad418",
                is_hardened_runtime=True,
                is_apple=False,
                is_valid=True,
                scan_proves_safe=False,
            ),
            MacAppSignatureInfo(
                bundle_id="com.user.CustomTool",
                bundle_path="/Applications/CustomTool.app",
                executable_path="/Applications/CustomTool.app/Contents/MacOS/CustomTool",
                signature_status=SignatureStatus.ADHOC_SIGNED,
                notarization_status=NotarizationStatus.NOT_APPLICABLE,
                authority_type=SigningAuthorityType.ADHOC,
                authorities=[],
                team_id=None,
                cdhash="c114f7704e688414bb41e980315aa6878b1d92bf",
                is_hardened_runtime=False,
                is_apple=False,
                is_valid=True,
                scan_proves_safe=False,
            ),
            MacAppSignatureInfo(
                bundle_id="com.unknown.UnsignedScript",
                bundle_path="/Applications/UnsignedScript.app",
                executable_path="/Applications/UnsignedScript.app/Contents/MacOS/run.sh",
                signature_status=SignatureStatus.UNSIGNED,
                notarization_status=NotarizationStatus.NOT_APPLICABLE,
                authority_type=SigningAuthorityType.UNSIGNED,
                authorities=[],
                team_id=None,
                cdhash=None,
                is_hardened_runtime=False,
                is_apple=False,
                is_valid=False,
                scan_proves_safe=False,
            ),
        ]

        validly_signed = sum(1 for s in signatures if s.signature_status == SignatureStatus.SIGNED_VALID)
        notarized = sum(1 for s in signatures if s.is_notarized)
        apple_system = sum(1 for s in signatures if s.notarization_status == NotarizationStatus.APPLE_SYSTEM)
        unsigned = sum(1 for s in signatures if s.signature_status == SignatureStatus.UNSIGNED)

        return MacAppSignatureReport(
            collection_method="MOCK_PLATFORM_ADAPTER",
            timestamp=datetime.now(timezone.utc).isoformat(),
            host_platform="Darwin-Mock-Apple-Silicon-arm64",
            signatures=signatures,
            inspected_apps_count=len(signatures),
            validly_signed_count=validly_signed,
            notarized_count=notarized,
            apple_system_count=apple_system,
            unsigned_count=unsigned,
            warnings=[],
            unavailable_telemetry=[],
        )

    def detect(
        self,
        bundle_paths: Optional[List[Path | str]] = None,
        apps: Optional[List[Path | str]] = None,
        max_apps: Optional[int] = None,
        mock: bool = False,
    ) -> MacAppSignatureReport:
        """Perform comprehensive read-only code signature and notarization inspection."""
        if mock or platform.system() != "Darwin":
            return self.detect_mock()

        target_inputs = apps if apps is not None else bundle_paths
        paths_to_inspect: List[Path] = []
        if target_inputs:
            for p in target_inputs:
                resolved = Path(p).resolve()
                if resolved.exists():
                    paths_to_inspect.append(resolved)
        else:
            # Check default system applications
            for default_p in self.DEFAULT_INSPECTION_PATHS:
                if default_p.exists():
                    paths_to_inspect.append(default_p)

        if max_apps is not None and max_apps > 0:
            paths_to_inspect = paths_to_inspect[:max_apps]

        signatures: List[MacAppSignatureInfo] = []
        warnings: List[str] = []
        unavailable: List[str] = []

        if not self.codesign_path.exists():
            unavailable.append(f"codesign utility not found at {self.codesign_path}")
        if not self.spctl_path.exists():
            unavailable.append(f"spctl utility not found at {self.spctl_path}")

        for path in paths_to_inspect:
            try:
                sig_info = self.inspect_bundle(path)
                signatures.append(sig_info)
            except Exception as exc:
                logger.warning(f"Failed to inspect bundle {path}: {exc}")
                warnings.append(f"Inspection error on {path}: {exc}")

        validly_signed = sum(1 for s in signatures if s.signature_status == SignatureStatus.SIGNED_VALID)
        notarized = sum(1 for s in signatures if s.is_notarized)
        apple_system = sum(1 for s in signatures if s.notarization_status == NotarizationStatus.APPLE_SYSTEM)
        unsigned = sum(1 for s in signatures if s.signature_status == SignatureStatus.UNSIGNED)

        return MacAppSignatureReport(
            collection_method="NATIVE_DARWIN_CODESIGN",
            timestamp=datetime.now(timezone.utc).isoformat(),
            host_platform=platform.platform(),
            signatures=signatures,
            inspected_apps_count=len(signatures),
            validly_signed_count=validly_signed,
            notarized_count=notarized,
            apple_system_count=apple_system,
            unsigned_count=unsigned,
            warnings=warnings,
            unavailable_telemetry=unavailable,
        )
