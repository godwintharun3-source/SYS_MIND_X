"""Read-only host environment inspector for SYSTEM MIND X.

Gathers hardware, operating system, security policy, and developer toolchain
telemetry using safe, non-privileged, read-only queries.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Dict, List, Optional

from system_mind.core.types import HostEnvironmentReport, PlatformTier


class MockHostAdapter:
    """Mock platform adapter for simulating diverse hosts without physical access."""

    def __init__(
        self,
        os_name: str = "Darwin",
        os_version: str = "27.0.1",
        kernel_version: str = "27.0.0",
        architecture: str = "arm64",
        cpu_brand: str = "Apple M1",
        cpu_cores: int = 8,
        memory_bytes: int = 8589934592,
        sip_enabled: Optional[bool] = True,
        gatekeeper_enabled: Optional[bool] = True,
        installed_tools: Optional[Dict[str, Optional[str]]] = None,
    ) -> None:
        self.os_name = os_name
        self.os_version = os_version
        self.kernel_version = kernel_version
        self.architecture = architecture
        self.cpu_brand = cpu_brand
        self.cpu_cores = cpu_cores
        self.memory_bytes = memory_bytes
        self.sip_enabled = sip_enabled
        self.gatekeeper_enabled = gatekeeper_enabled
        self.installed_tools = installed_tools or {
            "python3": "/usr/bin/python3",
            "git": "/usr/bin/git",
            "cargo": "/Users/mock/.cargo/bin/cargo",
            "rustc": "/Users/mock/.cargo/bin/rustc",
        }


class HostEnvironmentInspector:
    """Non-destructive, read-only environment inspector."""

    COMMON_TOOLS = [
        "python3",
        "pip",
        "pytest",
        "git",
        "cargo",
        "rustc",
        "go",
        "node",
        "nix",
        "docker",
        "colima",
        "podman",
        "qemu-system-aarch64",
        "qemu-system-x86_64",
    ]

    def __init__(self, mock_adapter: Optional[MockHostAdapter] = None) -> None:
        self._mock = mock_adapter

    def inspect(self) -> HostEnvironmentReport:
        """Execute read-only queries to construct a HostEnvironmentReport."""
        if self._mock:
            return self._build_mock_report(self._mock)

        return self._inspect_live_host()

    def _inspect_live_host(self) -> HostEnvironmentReport:
        os_name = platform.system()
        os_version = platform.mac_ver()[0] if os_name == "Darwin" else platform.version()
        kernel_version = platform.release()
        architecture = platform.machine()
        cpu_brand = self._get_cpu_brand(os_name)
        cpu_cores = os.cpu_count() or 1
        memory_bytes = self._get_memory_bytes(os_name)
        sip_enabled = self._get_sip_status(os_name)
        gatekeeper_enabled = self._get_gatekeeper_status(os_name)
        tools = self._detect_tools()

        platform_tier = self._classify_platform_tier(os_name, architecture)
        is_supported = platform_tier != PlatformTier.UNSUPPORTED

        notes: List[str] = []
        if os_name == "Darwin" and architecture == "arm64":
            notes.append("Host is verified Tier-1 primary development and companion target.")
        if sip_enabled:
            notes.append("macOS System Integrity Protection is enabled (authoritative kernel security).")
        if gatekeeper_enabled:
            notes.append("macOS Gatekeeper assessment is active.")

        return HostEnvironmentReport(
            os_name=os_name,
            os_version=os_version,
            kernel_version=kernel_version,
            architecture=architecture,
            cpu_brand=cpu_brand,
            cpu_cores=cpu_cores,
            memory_bytes=memory_bytes,
            sip_enabled=sip_enabled,
            gatekeeper_enabled=gatekeeper_enabled,
            platform_tier=platform_tier,
            installed_tools=tools,
            is_supported_host=is_supported,
            notes=notes,
        )

    def _build_mock_report(self, mock: MockHostAdapter) -> HostEnvironmentReport:
        platform_tier = self._classify_platform_tier(mock.os_name, mock.architecture)
        is_supported = platform_tier != PlatformTier.UNSUPPORTED
        notes = ["Simulated platform report via MockHostAdapter."]

        return HostEnvironmentReport(
            os_name=mock.os_name,
            os_version=mock.os_version,
            kernel_version=mock.kernel_version,
            architecture=mock.architecture,
            cpu_brand=mock.cpu_brand,
            cpu_cores=mock.cpu_cores,
            memory_bytes=mock.memory_bytes,
            sip_enabled=mock.sip_enabled,
            gatekeeper_enabled=mock.gatekeeper_enabled,
            platform_tier=platform_tier,
            installed_tools=mock.installed_tools,
            is_supported_host=is_supported,
            notes=notes,
        )

    def _classify_platform_tier(self, os_name: str, arch: str) -> PlatformTier:
        if os_name == "Darwin" and arch in ("arm64", "aarch64"):
            return PlatformTier.TIER_1_HOST_COMPANION
        elif os_name == "Windows" and arch in ("x86_64", "AMD64"):
            return PlatformTier.TIER_2_WINDOWS
        elif os_name == "Linux" and arch in ("x86_64", "amd64"):
            return PlatformTier.TIER_2_UBUNTU
        elif os_name == "Linux" and "nix" in arch.lower():
            return PlatformTier.TIER_3_NIXOS_VM
        return PlatformTier.UNSUPPORTED

    def _get_cpu_brand(self, os_name: str) -> str:
        if os_name == "Darwin":
            try:
                res = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                brand = res.stdout.strip()
                if brand:
                    return brand
            except Exception:
                pass
        return platform.processor() or "Unknown CPU"

    def _get_memory_bytes(self, os_name: str) -> int:
        if os_name == "Darwin":
            try:
                res = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip().isdigit():
                    return int(res.stdout.strip())
            except Exception:
                pass
        return 0

    def _get_sip_status(self, os_name: str) -> Optional[bool]:
        if os_name != "Darwin":
            return None
        try:
            res = subprocess.run(
                ["csrutil", "status"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            return "enabled" in res.stdout.lower()
        except Exception:
            return None

    def _get_gatekeeper_status(self, os_name: str) -> Optional[bool]:
        if os_name != "Darwin":
            return None
        try:
            res = subprocess.run(
                ["spctl", "--status"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            return "assessments enabled" in res.stdout.lower()
        except Exception:
            return None

    def _detect_tools(self) -> Dict[str, Optional[str]]:
        results: Dict[str, Optional[str]] = {}
        for tool in self.COMMON_TOOLS:
            path = shutil.which(tool)
            results[tool] = path
        return results
