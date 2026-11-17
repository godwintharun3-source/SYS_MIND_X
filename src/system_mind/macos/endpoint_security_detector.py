"""Read-only macOS Endpoint Security integration feasibility and entitlement inspector."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.endpoint_security_models import (
    EsActionType,
    EsClientResultCode,
    EsEntitlementCheck,
    EsEventSample,
    EsEventType,
    EsFeasibilityReport,
    EsStatus,
)

logger = logging.getLogger(__name__)

FRAMEWORK_PATHS = [
    "/System/Library/Frameworks/EndpointSecurity.framework",
    "/usr/lib/libEndpointSecurity.dylib",
]

ENDPOINT_SECURITY_ENTITLEMENT = "com.apple.developer.endpoint-security.client"


class MacEndpointSecurityDetector:
    """Read-only inspector evaluating macOS Endpoint Security feasibility, entitlement constraints, and fallback telemetry."""

    def __init__(self, target_binary_path: Optional[str] = None) -> None:
        self.target_binary_path = target_binary_path or sys.executable

    def inspect_entitlements(self, binary_path: Optional[str] = None) -> EsEntitlementCheck:
        """Audit host entitlement, privilege, SIP, and framework availability without mutating host settings."""
        target = binary_path or self.target_binary_path
        uid = os.geteuid() if hasattr(os, "geteuid") else 1000
        is_root = (uid == 0)

        # Check framework existence
        framework_present = False
        resolved_fw_path = "None"
        for fw_path in FRAMEWORK_PATHS:
            if Path(fw_path).exists():
                framework_present = True
                resolved_fw_path = fw_path
                break

        # Check SIP status safely
        sip_enabled, sip_raw = self._check_sip_status()

        # Check binary entitlements via codesign
        has_es_entitlement, team_id, codesign_diag = self._check_binary_entitlements(target)

        # Evaluate TCC Full Disk Access probability
        tcc_fda_probable = self._check_fda_accessibility()

        diagnostics: List[str] = [
            f"Process UID: {uid} ({'root' if is_root else 'unprivileged user companion'})",
            f"System Integrity Protection (SIP): {sip_raw}",
            f"EndpointSecurity Library: {'Present at ' + resolved_fw_path if framework_present else 'Absent'}",
            f"Entitlement '{ENDPOINT_SECURITY_ENTITLEMENT}': {'Present' if has_es_entitlement else 'Missing (Requires Apple Developer Grant)'}",
        ]
        if team_id:
            diagnostics.append(f"Signing Team ID: {team_id}")
        if codesign_diag:
            diagnostics.append(f"CodeSign Info: {codesign_diag}")
        diagnostics.append(f"TCC Full Disk Access: {'Accessible' if tcc_fda_probable else 'Restricted / User Scope'}")

        return EsEntitlementCheck(
            has_endpoint_security_entitlement=has_es_entitlement,
            is_root=is_root,
            uid=uid,
            sip_enabled=sip_enabled,
            sip_status_raw=sip_raw,
            tcc_full_disk_access_probable=tcc_fda_probable,
            framework_binary_present=framework_present,
            framework_path=resolved_fw_path,
            entitlement_key=ENDPOINT_SECURITY_ENTITLEMENT,
            team_id=team_id,
            diagnostics=diagnostics,
        )

    def _check_sip_status(self) -> Tuple[bool, str]:
        """Query Darwin System Integrity Protection status via /usr/bin/csrutil."""
        if platform.system() != "Darwin":
            return False, "Non-Darwin Host (SIP Not Applicable)"

        csrutil_bin = "/usr/bin/csrutil"
        if not Path(csrutil_bin).exists():
            return True, "Unknown (/usr/bin/csrutil missing)"

        try:
            res = subprocess.run(
                [csrutil_bin, "status"],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            raw = res.stdout.strip() or res.stderr.strip() or "Unknown"
            is_enabled = "enabled" in raw.lower()
            return is_enabled, raw
        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("csrutil status query failed or timed out: %s", e)
            return True, f"Query error: {e}"

    def _check_binary_entitlements(self, binary_path: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Inspect code signature entitlements and Team ID of target binary via /usr/bin/codesign."""
        if platform.system() != "Darwin" or not Path(binary_path).exists():
            return False, None, "Target binary inspection skipped (non-Darwin or non-existent path)"

        codesign_bin = "/usr/bin/codesign"
        if not Path(codesign_bin).exists():
            return False, None, "codesign binary unavailable"

        has_entitlement = False
        team_id = None
        diag_msg = None

        try:
            # Query entitlements XML
            ent_res = subprocess.run(
                [codesign_bin, "-d", "--entitlements", ":-", binary_path],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            xml_output = ent_res.stdout
            if ENDPOINT_SECURITY_ENTITLEMENT in xml_output and "<true/>" in xml_output:
                has_entitlement = True

            # Query Team ID & Signing Info
            sign_res = subprocess.run(
                [codesign_bin, "-dv", binary_path],
                capture_output=True,
                text=True,
                timeout=3.0,
                check=False,
            )
            combined_stderr = sign_res.stderr
            for line in combined_stderr.splitlines():
                line = line.strip()
                if line.startswith("TeamIdentifier="):
                    team_id = line.split("=", 1)[1]
                elif line.startswith("Authority=") and not diag_msg:
                    diag_msg = line

        except (subprocess.TimeoutExpired, OSError) as e:
            logger.debug("codesign inspection failed: %s", e)
            diag_msg = f"Inspection failed: {e}"

        return has_entitlement, team_id, diag_msg

    def _check_fda_accessibility(self) -> bool:
        """Check whether the process has Full Disk Access by testing read permission on protected directory."""
        if platform.system() != "Darwin":
            return False
        protected_probe = Path("/Library/Application Support/com.apple.TCC/TCC.db")
        try:
            return protected_probe.exists() and os.access(protected_probe, os.R_OK)
        except (OSError, PermissionError):
            return False

    def detect(self, use_mock: bool = False, profile: str = "restricted_companion") -> EsFeasibilityReport:
        """Evaluate Endpoint Security feasibility and generate comprehensive audit report with fallback mapping."""
        now_iso = datetime.now(timezone.utc).isoformat()

        if use_mock:
            return self._generate_mock_report(profile=profile, timestamp=now_iso)

        if platform.system() != "Darwin":
            return EsFeasibilityReport(
                status=EsStatus.UNAVAILABLE_PLATFORM,
                result_code=EsClientResultCode.ERR_INTERNAL,
                entitlement_check=EsEntitlementCheck(
                    has_endpoint_security_entitlement=False,
                    is_root=False,
                    uid=1000,
                    sip_enabled=False,
                    sip_status_raw="Non-Darwin Kernel",
                    tcc_full_disk_access_probable=False,
                    framework_binary_present=False,
                    framework_path="None",
                    diagnostics=["Endpoint Security framework is proprietary to Apple Darwin (macOS 10.15+)"],
                ),
                supported_event_types=[],
                fallback_strategies={
                    "filesystem": "eBPF / inotify (Linux) or USN Journal (Windows)",
                    "process_lifecycle": "procfs (/proc) or Windows Toolhelp API",
                },
                sample_events=[],
                timestamp=now_iso,
                unavailable_telemetry=["apple_endpoint_security_framework", "darwin_kernel_auditing"],
                host_platform=platform.system(),
                scan_proves_safe=False,
                is_mock=False,
            )

        ent_check = self.inspect_entitlements()

        # Evaluate Darwin ES Client Feasibility
        if not ent_check.is_root:
            status = EsStatus.RESTRICTED_NOT_ROOT
            result_code = EsClientResultCode.ERR_NOT_PRIVILEGED
        elif not ent_check.has_endpoint_security_entitlement:
            status = EsStatus.RESTRICTED_MISSING_ENTITLEMENT
            result_code = EsClientResultCode.ERR_NOT_ENTITLED
        elif not ent_check.framework_binary_present:
            status = EsStatus.UNAVAILABLE_PLATFORM
            result_code = EsClientResultCode.ERR_INTERNAL
        else:
            status = EsStatus.AVAILABLE_ENTITLED
            result_code = EsClientResultCode.SUCCESS

        supported_types = [
            EsEventType.NOTIFY_EXEC,
            EsEventType.NOTIFY_OPEN,
            EsEventType.NOTIFY_FORK,
            EsEventType.NOTIFY_EXIT,
            EsEventType.NOTIFY_CREATE,
            EsEventType.NOTIFY_CLOSE,
            EsEventType.NOTIFY_UNLINK,
        ]

        fallback_strategies = {
            "filesystem": "Apple CoreServices FSEvents (MacFsEventsDetector) - Passive unprivileged change notifications",
            "process_lifecycle": "Darwin sysctl / /bin/ps (MacProcessDetector) - Unprivileged process telemetry",
            "service_lifecycle": "Darwin launchctl / LaunchDaemons scan (MacServicesDetector) - Service inventory",
            "signature_validation": "Darwin codesign / spctl (MacSignaturesDetector) - Provenance verification",
        }

        unavailable_telemetry: List[str] = []
        if status != EsStatus.AVAILABLE_ENTITLED:
            unavailable_telemetry.extend([
                "kernel_auth_interception",
                "realtime_es_event_stream",
                "low_level_vnode_auth",
            ])

        return EsFeasibilityReport(
            status=status,
            result_code=result_code,
            entitlement_check=ent_check,
            supported_event_types=supported_types,
            fallback_strategies=fallback_strategies,
            sample_events=[],
            timestamp=now_iso,
            unavailable_telemetry=unavailable_telemetry,
            host_platform="Darwin",
            scan_proves_safe=False,
            is_mock=False,
        )

    def _generate_mock_report(self, profile: str, timestamp: str) -> EsFeasibilityReport:
        """Generate deterministic mock report for test isolation and multi-platform simulation."""
        if profile == "entitled_daemon":
            ent_check = EsEntitlementCheck(
                has_endpoint_security_entitlement=True,
                is_root=True,
                uid=0,
                sip_enabled=True,
                sip_status_raw="System Integrity Protection status: enabled.",
                tcc_full_disk_access_probable=True,
                framework_binary_present=True,
                framework_path="/System/Library/Frameworks/EndpointSecurity.framework",
                team_id="EQHXZ8M8AV",
                diagnostics=[
                    "Process UID: 0 (root privileged system daemon)",
                    "SIP: System Integrity Protection status: enabled.",
                    "EndpointSecurity Library: Present at /System/Library/Frameworks/EndpointSecurity.framework",
                    "Entitlement 'com.apple.developer.endpoint-security.client': Present (Signed by Apple)",
                    "Signing Team ID: EQHXZ8M8AV",
                    "TCC Full Disk Access: Accessible via MDM profile",
                ],
            )
            sample_events = [
                EsEventSample(
                    event_id="ES-EV-001",
                    event_type=EsEventType.NOTIFY_EXEC,
                    action_type=EsActionType.NOTIFY,
                    timestamp=timestamp,
                    process_pid=1024,
                    process_ppid=1,
                    executable_path="/usr/bin/git",
                    target_path=None,
                    cdhash="0123456789abcdef0123456789abcdef01234567",
                    signing_id="com.apple.git",
                    team_id=None,
                    is_platform_binary=True,
                ),
                EsEventSample(
                    event_id="ES-EV-002",
                    event_type=EsEventType.NOTIFY_CREATE,
                    action_type=EsActionType.NOTIFY,
                    timestamp=timestamp,
                    process_pid=2048,
                    process_ppid=501,
                    executable_path="/Applications/Visual Studio Code.app/Contents/MacOS/Electron",
                    target_path="/tmp/scratch_buffer.py",
                    cdhash="fedcba9876543210fedcba9876543210fedcba98",
                    signing_id="com.microsoft.VSCode",
                    team_id="UBF8T346G9",
                    is_platform_binary=False,
                ),
            ]
            return EsFeasibilityReport(
                status=EsStatus.AVAILABLE_ENTITLED,
                result_code=EsClientResultCode.SUCCESS,
                entitlement_check=ent_check,
                supported_event_types=[
                    EsEventType.NOTIFY_EXEC,
                    EsEventType.NOTIFY_OPEN,
                    EsEventType.NOTIFY_FORK,
                    EsEventType.NOTIFY_EXIT,
                    EsEventType.NOTIFY_CREATE,
                    EsEventType.NOTIFY_CLOSE,
                    EsEventType.NOTIFY_UNLINK,
                ],
                fallback_strategies={
                    "filesystem": "Apple CoreServices FSEvents (MacFsEventsDetector)",
                    "process_lifecycle": "Darwin sysctl / /bin/ps (MacProcessDetector)",
                },
                sample_events=sample_events,
                timestamp=timestamp,
                unavailable_telemetry=[],
                host_platform="Darwin",
                scan_proves_safe=False,
                is_mock=True,
            )

        elif profile == "unsupported_platform":
            return EsFeasibilityReport(
                status=EsStatus.UNAVAILABLE_PLATFORM,
                result_code=EsClientResultCode.ERR_INTERNAL,
                entitlement_check=EsEntitlementCheck(
                    has_endpoint_security_entitlement=False,
                    is_root=False,
                    uid=1000,
                    sip_enabled=False,
                    sip_status_raw="Linux kernel (SIP Not Applicable)",
                    tcc_full_disk_access_probable=False,
                    framework_binary_present=False,
                    framework_path="None",
                    diagnostics=["Host OS is Linux; Apple EndpointSecurity.framework is unsupported."],
                ),
                supported_event_types=[],
                fallback_strategies={
                    "filesystem": "eBPF / inotify (Linux) or USN Journal (Windows)",
                    "process_lifecycle": "procfs (/proc)",
                },
                sample_events=[],
                timestamp=timestamp,
                unavailable_telemetry=["apple_endpoint_security_framework", "darwin_kernel_auditing"],
                host_platform="Linux",
                scan_proves_safe=False,
                is_mock=True,
            )

        # Default profile: "restricted_companion"
        ent_check = EsEntitlementCheck(
            has_endpoint_security_entitlement=False,
            is_root=False,
            uid=501,
            sip_enabled=True,
            sip_status_raw="System Integrity Protection status: enabled.",
            tcc_full_disk_access_probable=False,
            framework_binary_present=True,
            framework_path="/System/Library/Frameworks/EndpointSecurity.framework",
            team_id=None,
            diagnostics=[
                "Process UID: 501 (unprivileged user companion agent)",
                "SIP: System Integrity Protection status: enabled.",
                "EndpointSecurity Library: Present at /System/Library/Frameworks/EndpointSecurity.framework",
                "Entitlement 'com.apple.developer.endpoint-security.client': Missing (requires Apple approval)",
                "Notice: Least-privilege companion architecture delegates to FSEvents and sysctl",
            ],
        )
        return EsFeasibilityReport(
            status=EsStatus.RESTRICTED_NOT_ROOT,
            result_code=EsClientResultCode.ERR_NOT_PRIVILEGED,
            entitlement_check=ent_check,
            supported_event_types=[
                EsEventType.NOTIFY_EXEC,
                EsEventType.NOTIFY_OPEN,
                EsEventType.NOTIFY_FORK,
                EsEventType.NOTIFY_EXIT,
                EsEventType.NOTIFY_CREATE,
            ],
            fallback_strategies={
                "filesystem": "Apple CoreServices FSEvents (MacFsEventsDetector) - Passive unprivileged change notifications",
                "process_lifecycle": "Darwin sysctl / /bin/ps (MacProcessDetector) - Unprivileged process telemetry",
                "service_lifecycle": "Darwin launchctl / LaunchDaemons scan (MacServicesDetector) - Service inventory",
                "signature_validation": "Darwin codesign / spctl (MacSignaturesDetector) - Provenance verification",
            },
            sample_events=[],
            timestamp=timestamp,
            unavailable_telemetry=[
                "kernel_auth_interception",
                "realtime_es_event_stream",
                "low_level_vnode_auth",
            ],
            host_platform="Darwin",
            scan_proves_safe=False,
            is_mock=True,
        )
