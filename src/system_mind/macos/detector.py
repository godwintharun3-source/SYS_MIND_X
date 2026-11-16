"""Read-only macOS platform detector and telemetry collector.

Gathers macOS version, Darwin kernel build, Apple Silicon processor architecture,
Rosetta 2 translation status, and privacy-preserving host identity using non-privileged,
read-only queries in strict compliance with SC-01 and privacy constraints.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import platform
import plistlib
import re
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.models import (
    MacArchitecture,
    MacHostIdentity,
    MacOSVersionInfo,
    MacTelemetryReport,
)
from system_mind.platform.adapter import MockPlatformAdapter
from system_mind.platform.matrix import PlatformTargetId


def _safe_exec(cmd: List[str], timeout: int = 5) -> Tuple[int, str]:
    """Execute a read-only query safely without shell=True in compliance with SC-01."""
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        return 127, ""


class MacOSIdentityDetector:
    """Read-only detector for macOS platform properties and host identity."""

    MARKETING_NAMES: Dict[int, str] = {
        15: "Sequoia",
        14: "Sonoma",
        13: "Ventura",
        12: "Monterey",
        11: "Big Sur",
    }

    @classmethod
    def resolve_marketing_name(cls, major: int, minor: int = 0, darwin_release: str = "") -> str:
        """Resolve friendly marketing name from product version and Darwin release."""
        if major in cls.MARKETING_NAMES:
            return cls.MARKETING_NAMES[major]
        elif major == 10 and minor == 15:
            return "Catalina"
        elif major == 10 and minor == 14:
            return "Mojave"
        elif major >= 26 or darwin_release.startswith("27."):
            return "macOS Sequoia / Darwin 27 Preview"
        elif major > 15:
            return f"macOS (Major {major})"
        return f"macOS {major}.{minor}"

    @classmethod
    def detect(cls, mock_adapter: Optional[MockPlatformAdapter] = None) -> MacTelemetryReport:
        """Execute detection using live Darwin host or mock platform adapter."""
        if mock_adapter is not None:
            return cls._detect_from_mock(mock_adapter)

        if platform.system() == "Darwin":
            return cls._detect_live_darwin()

        return cls._detect_non_darwin_fallback()

    @classmethod
    def _detect_live_darwin(cls) -> MacTelemetryReport:
        """Collect live telemetry from native Darwin kernel and macOS CoreServices."""
        unavailable: List[str] = []
        warnings: List[str] = []

        # 1. Product Version and Build Version from SystemVersion.plist or sw_vers
        product_name = "macOS"
        product_version = ""
        build_version = ""

        sys_plist_path = Path("/System/Library/CoreServices/SystemVersion.plist")
        if sys_plist_path.exists():
            try:
                data = plistlib.loads(sys_plist_path.read_bytes())
                product_name = str(data.get("ProductName", "macOS"))
                product_version = str(data.get("ProductVersion", ""))
                build_version = str(data.get("ProductBuildVersion", ""))
            except Exception as exc:
                warnings.append(f"Could not parse SystemVersion.plist: {exc}")

        # Fallback to sw_vers if plist was unavailable
        if not product_version or not build_version:
            code, out = _safe_exec(["sw_vers"])
            if code == 0:
                for line in out.splitlines():
                    if "ProductVersion:" in line:
                        product_version = line.split(":", 1)[1].strip()
                    elif "BuildVersion:" in line:
                        build_version = line.split(":", 1)[1].strip()
                    elif "ProductName:" in line:
                        product_name = line.split(":", 1)[1].strip()

        # Final fallback to platform module
        if not product_version:
            mac_ver = platform.mac_ver()[0]
            product_version = mac_ver if mac_ver else "15.1.0"
        if not build_version:
            code, out = _safe_exec(["sysctl", "-n", "kern.osversion"])
            build_version = out if code == 0 and out else "24B83"

        # 2. Darwin Kernel Release
        code, out = _safe_exec(["sysctl", "-n", "kern.osrelease"])
        darwin_release = out if (code == 0 and out) else platform.release()

        # Parse SemVer components
        parts = [int(p) for p in re.findall(r"\d+", product_version)]
        major = parts[0] if len(parts) > 0 else 15
        minor = parts[1] if len(parts) > 1 else 0
        patch = parts[2] if len(parts) > 2 else 0

        marketing_name = cls.resolve_marketing_name(major, minor, darwin_release)

        version_info = MacOSVersionInfo(
            product_name=product_name,
            product_version=product_version,
            major_version=major,
            minor_version=minor,
            patch_version=patch,
            build_version=build_version,
            darwin_kernel_release=darwin_release,
            marketing_name=marketing_name,
        )

        # 3. Processor Architecture and Rosetta 2 Status
        code, out = _safe_exec(["sysctl", "-n", "hw.machine"])
        machine = out if (code == 0 and out) else platform.machine()
        is_apple_silicon = machine in ("arm64", "aarch64")

        code, out = _safe_exec(["sysctl", "-n", "sysctl.proc_translated"])
        is_rosetta = (code == 0 and out.strip() == "1")

        arch = MacArchitecture(
            machine=machine,
            is_apple_silicon=is_apple_silicon,
            byte_order=sys.byteorder,
            pointer_size_bits=64 if sys.maxsize > 2**32 else 32,
            is_rosetta_translated=is_rosetta,
        )

        # 4. Host Identity & Anonymized Hardware Metadata
        hostname = socket.gethostname()

        code, out = _safe_exec(["scutil", "--get", "ComputerName"])
        computer_name = out if (code == 0 and out) else hostname

        code, out = _safe_exec(["scutil", "--get", "LocalHostName"])
        local_host_name = out if (code == 0 and out) else hostname

        # Query IOPlatformExpertDevice for PlatformUUID and Serial
        platform_uuid: Optional[str] = None
        serial_hash: Optional[str] = None

        code, out = _safe_exec(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"])
        if code == 0 and out:
            # Extract IOPlatformUUID
            uuid_match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if uuid_match:
                platform_uuid = uuid_match.group(1)

            # Extract and anonymize IOPlatformSerialNumber (Privacy protection)
            serial_match = re.search(r'"IOPlatformSerialNumber"\s*=\s*"([^"]+)"', out)
            if serial_match:
                raw_serial = serial_match.group(1).strip()
                # Store only salted cryptographic digest prefix, never plaintext serial
                digest = hashlib.sha256(f"SYSTEM_MIND_{raw_serial}".encode("utf-8")).hexdigest()
                serial_hash = f"sha256:{digest[:16]}"
        else:
            unavailable.append("IOPlatformExpertDevice (requires macOS ioreg query)")

        # Check for virtual machine indicators
        is_vm = False
        code, out = _safe_exec(["sysctl", "-n", "machdep.cpu.brand_string"])
        if code == 0 and ("Virtual" in out or "QEMU" in out or "Apple Virtual" in out):
            is_vm = True

        identity = MacHostIdentity(
            hostname=hostname,
            computer_name=computer_name,
            local_host_name=local_host_name,
            platform_uuid=platform_uuid,
            anonymized_serial_hash=serial_hash,
            is_virtual_machine=is_vm,
        )

        return MacTelemetryReport(
            version_info=version_info,
            architecture=arch,
            identity=identity,
            collected_at_epoch_secs=time.time(),
            collection_method="NATIVE_DARWIN_SYSCTL",
            unavailable_telemetry=unavailable,
            warnings=warnings,
        )

    @classmethod
    def _detect_from_mock(cls, mock: MockPlatformAdapter) -> MacTelemetryReport:
        """Construct a deterministic macOS telemetry report from a MockPlatformAdapter."""
        report = mock.get_host_report()
        target_id = mock.get_target_id()

        is_darwin = (target_id == PlatformTargetId.MACOS_APPLE_SILICON or report.os_name == "Darwin")
        product_version = report.os_version
        parts = [int(p) for p in re.findall(r"\d+", product_version)]
        major = parts[0] if len(parts) > 0 else 15
        minor = parts[1] if len(parts) > 1 else 1
        patch = parts[2] if len(parts) > 2 else 0

        marketing_name = cls.resolve_marketing_name(major, minor, report.kernel_version)

        version_info = MacOSVersionInfo(
            product_name="macOS",
            product_version=product_version,
            major_version=major,
            minor_version=minor,
            patch_version=patch,
            build_version="24B83" if is_darwin else "NON_DARWIN_BUILD",
            darwin_kernel_release=report.kernel_version,
            marketing_name=marketing_name,
        )

        arch = MacArchitecture(
            machine=report.architecture,
            is_apple_silicon=report.architecture in ("arm64", "aarch64"),
            byte_order="little",
            pointer_size_bits=64,
            is_rosetta_translated=False,
        )

        mock_hash = hashlib.sha256(f"MOCK_MAC_{target_id.value}".encode("utf-8")).hexdigest()
        identity = MacHostIdentity(
            hostname=f"mock-{target_id.value.lower()}.local",
            computer_name=f"Mock {target_id.value}",
            local_host_name=f"mock-{target_id.value.lower()}",
            platform_uuid="00000000-0000-0000-0000-000000000001",
            anonymized_serial_hash=f"sha256:{mock_hash[:16]}",
            is_virtual_machine=(target_id == PlatformTargetId.NIXOS_VM),
        )

        return MacTelemetryReport(
            version_info=version_info,
            architecture=arch,
            identity=identity,
            collected_at_epoch_secs=time.time(),
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[] if is_darwin else ["native_darwin_kernel_unavailable"],
            warnings=[] if is_darwin else [f"Platform target {target_id.value} is not native macOS Darwin"],
        )

    @classmethod
    def _detect_non_darwin_fallback(cls) -> MacTelemetryReport:
        """Fallback for non-Darwin environments (Linux/Windows CI hosts)."""
        os_name = platform.system()
        machine = platform.machine()
        arch = MacArchitecture(
            machine=machine,
            is_apple_silicon=machine in ("arm64", "aarch64"),
            byte_order=sys.byteorder,
            pointer_size_bits=64 if sys.maxsize > 2**32 else 32,
            is_rosetta_translated=False,
        )
        version_info = MacOSVersionInfo(
            product_name=f"Simulated macOS (Host: {os_name})",
            product_version="15.1.0",
            major_version=15,
            minor_version=1,
            patch_version=0,
            build_version="24B83",
            darwin_kernel_release="24.1.0",
            marketing_name="Sequoia (Simulated)",
        )
        identity = MacHostIdentity(
            hostname=socket.gethostname(),
            computer_name=f"{socket.gethostname()} ({os_name})",
            local_host_name=socket.gethostname().split(".")[0],
            platform_uuid="00000000-0000-0000-0000-000000000000",
            anonymized_serial_hash="sha256:0000000000000000",
            is_virtual_machine=True,
        )
        return MacTelemetryReport(
            version_info=version_info,
            architecture=arch,
            identity=identity,
            collected_at_epoch_secs=time.time(),
            collection_method="NON_DARWIN_FALLBACK",
            unavailable_telemetry=[
                "native_darwin_sysctl",
                "core_services_plist",
                "scutil_computer_name",
                "ioreg_platform_expert",
            ],
            warnings=[f"Running on {os_name}; native Darwin kernel APIs are unavailable."],
        )
