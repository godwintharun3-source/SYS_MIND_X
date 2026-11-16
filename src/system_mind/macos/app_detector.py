"""Read-only macOS installed application inventory and bundle identifier detector."""

from __future__ import annotations

import logging
from pathlib import Path
import platform
import plistlib
import subprocess
import time
from typing import Any, Dict, List, Optional, Set

from system_mind.core.types import ComponentOwnership
from system_mind.macos.app_models import (
    ApplicationCategory,
    MacAppInfo,
    MacAppInventoryReport,
)

logger = logging.getLogger(__name__)


class MacAppDetector:
    """Read-only, passive introspection engine for macOS installed application bundles."""

    DEFAULT_APP_ROOTS: List[Path] = [
        Path("/Applications"),
        Path("/System/Applications"),
        Path("/System/Applications/Utilities"),
        Path.home() / "Applications",
        Path("/System/Library/CoreServices/Applications"),
    ]

    def classify_category(self, bundle_id: str, name: str, bundle_path: Path) -> ApplicationCategory:
        """Categorize application into functional application category."""
        bid = bundle_id.lower()
        name_lower = name.lower()
        path_str = str(bundle_path)

        # Web browsers
        if any(
            b in bid
            for b in (
                "browser",
                "chrome",
                "safari",
                "firefox",
                "edge",
                "brave",
                "opera",
            )
        ):
            return ApplicationCategory.WEB_BROWSER

        # Developer tools & IDEs
        if any(
            d in bid
            for d in (
                "vscode",
                "xcode",
                "sublime",
                "jetbrains",
                "intellij",
                "pycharm",
                "terminal",
                "iterm",
                "docker",
                "postman",
                "github",
            )
        ) or any(
            term in name_lower
            for term in ("code", "terminal", "iterm", "developer", "xcode", "antigravity")
        ):
            return ApplicationCategory.DEVELOPER_TOOL

        # System utilities
        if "/utilities" in path_str.lower() or any(
            u in bid for u in ("activitymonitor", "diskutility", "console", "keychainaccess")
        ):
            return ApplicationCategory.UTILITY

        # Media & entertainment
        if any(
            m in bid
            for m in (
                "music",
                "spotify",
                "vlc",
                "quicktime",
                "tv",
                "photos",
                "podcast",
                "video",
            )
        ):
            return ApplicationCategory.MEDIA

        # Productivity & office
        if any(
            p in bid
            for p in (
                "slack",
                "notion",
                "word",
                "excel",
                "powerpoint",
                "notes",
                "mail",
                "calendar",
                "reminders",
                "pages",
                "numbers",
                "keynote",
            )
        ):
            return ApplicationCategory.PRODUCTIVITY

        # Core OS system applications
        if path_str.startswith("/System/") or bid.startswith("com.apple."):
            return ApplicationCategory.CORE_SYSTEM

        return ApplicationCategory.OTHER

    def classify_ownership(
        self,
        bundle_id: str,
        bundle_path: Path,
    ) -> tuple[ComponentOwnership, bool, bool]:
        """Classify component ownership, Apple status, and user-app immunity status."""
        path_str = str(bundle_path)
        bid = bundle_id.lower()

        # System-managed Apple applications
        if path_str.startswith("/System/") or bid.startswith("com.apple."):
            return ComponentOwnership.SYSTEM_MANAGED, True, False

        # User-managed applications in home directory
        if "/Users/" in path_str or str(Path.home()) in path_str:
            return ComponentOwnership.USER_MANAGED, False, True

        # Vendor-managed system-wide third-party applications
        return ComponentOwnership.VENDOR_MANAGED, False, True

    def scan_bundle(self, bundle_path: Path) -> Optional[MacAppInfo]:
        """Safely parse a single macOS application bundle's Info.plist."""
        if not bundle_path.is_dir() or bundle_path.suffix != ".app":
            return None

        plist_path = bundle_path / "Contents" / "Info.plist"
        if not plist_path.exists():
            return None

        try:
            with open(plist_path, "rb") as fp:
                data = plistlib.load(fp)

            if not isinstance(data, dict):
                return None

            # Extract bundle identifier
            bundle_id = data.get("CFBundleIdentifier")
            if not bundle_id or not isinstance(bundle_id, str):
                # Fallback to normalized stem if bundle identifier missing
                bundle_id = f"local.{bundle_path.stem.lower()}"

            # Extract display name
            name = (
                data.get("CFBundleDisplayName")
                or data.get("CFBundleName")
                or bundle_path.stem
            )
            if not isinstance(name, str) or not name.strip():
                name = bundle_path.stem

            # Extract versioning
            version = data.get("CFBundleShortVersionString") or data.get("CFBundleVersion") or "Unknown"
            if not isinstance(version, str):
                version = str(version)

            build_version = data.get("CFBundleVersion")
            if build_version is not None and not isinstance(build_version, str):
                build_version = str(build_version)

            # Executable paths
            executable_name = data.get("CFBundleExecutable")
            executable_path: Optional[str] = None
            if isinstance(executable_name, str):
                candidate_exec = bundle_path / "Contents" / "MacOS" / executable_name
                if candidate_exec.exists():
                    executable_path = str(candidate_exec)

            min_os_version = data.get("LSMinimumSystemVersion")
            if min_os_version is not None and not isinstance(min_os_version, str):
                min_os_version = str(min_os_version)

            ownership, is_apple, is_user_app = self.classify_ownership(bundle_id, bundle_path)
            category = self.classify_category(bundle_id, name, bundle_path)

            return MacAppInfo(
                name=name,
                bundle_id=bundle_id,
                bundle_path=str(bundle_path),
                version=version,
                build_version=build_version,
                executable_name=executable_name,
                executable_path=executable_path,
                min_os_version=min_os_version,
                ownership=ownership,
                category=category,
                is_apple=is_apple,
                is_user_app=is_user_app,
            )
        except Exception as exc:
            logger.debug(f"Failed to parse bundle {bundle_path}: {exc}")
            return None

    def query_mdfind_bundles(self) -> List[Path]:
        """Query Spotlight for application bundle paths if available."""
        if platform.system() != "Darwin":
            return []

        try:
            cmd = ["/usr/bin/mdfind", "kMDItemContentType == 'com.apple.application-bundle'"]
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if res.returncode == 0:
                paths: List[Path] = []
                for line in res.stdout.splitlines():
                    p_str = line.strip()
                    if p_str and p_str.endswith(".app"):
                        paths.append(Path(p_str))
                return paths
        except Exception as exc:
            logger.debug(f"mdfind query failed: {exc}")

        return []

    def scan_directories(self, roots: Optional[List[Path]] = None) -> List[MacAppInfo]:
        """Scan standard macOS application roots and deduplicate discovered bundles."""
        if roots is None:
            roots = self.DEFAULT_APP_ROOTS

        candidate_paths: Set[Path] = set()

        for root in roots:
            if not root.exists() or not root.is_dir():
                continue

            try:
                # Top-level .app bundles
                for entry in root.glob("*.app"):
                    candidate_paths.add(entry.resolve())

                # Single-level subdirectories (e.g. /Applications/Utilities/)
                for subdir in root.iterdir():
                    if subdir.is_dir() and not subdir.name.endswith(".app"):
                        for sub_entry in subdir.glob("*.app"):
                            candidate_paths.add(sub_entry.resolve())
            except (PermissionError, OSError) as exc:
                logger.debug(f"Permission error scanning {root}: {exc}")

        # Supplement with mdfind if on Darwin
        spotlight_paths = self.query_mdfind_bundles()
        for sp in spotlight_paths:
            # Only include applications from standard roots or top-level dirs
            p_str = str(sp)
            if any(p_str.startswith(str(r)) for r in roots) or p_str.startswith("/Applications"):
                candidate_paths.add(sp.resolve())

        apps: List[MacAppInfo] = []
        for path in sorted(candidate_paths, key=lambda p: str(p).lower()):
            app_info = self.scan_bundle(path)
            if app_info is not None:
                apps.append(app_info)

        return apps

    def detect_mock(self, mock_adapter: Optional[Any] = None) -> MacAppInventoryReport:
        """Construct deterministic Apple Silicon application inventory mock."""
        apps: List[MacAppInfo] = [
            MacAppInfo(
                name="Safari",
                bundle_id="com.apple.Safari",
                bundle_path="/System/Applications/Safari.app",
                version="18.0",
                build_version="20619.1.26.31.7",
                executable_name="Safari",
                executable_path="/System/Applications/Safari.app/Contents/MacOS/Safari",
                min_os_version="15.0",
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                category=ApplicationCategory.WEB_BROWSER,
                is_apple=True,
                is_user_app=False,
            ),
            MacAppInfo(
                name="Terminal",
                bundle_id="com.apple.Terminal",
                bundle_path="/System/Applications/Utilities/Terminal.app",
                version="2.15",
                build_version="453",
                executable_name="Terminal",
                executable_path="/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal",
                min_os_version="15.0",
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                category=ApplicationCategory.DEVELOPER_TOOL,
                is_apple=True,
                is_user_app=False,
            ),
            MacAppInfo(
                name="Finder",
                bundle_id="com.apple.finder",
                bundle_path="/System/Library/CoreServices/Finder.app",
                version="15.0",
                build_version="1732.1.3",
                executable_name="Finder",
                executable_path="/System/Library/CoreServices/Finder.app/Contents/MacOS/Finder",
                min_os_version="15.0",
                ownership=ComponentOwnership.SYSTEM_MANAGED,
                category=ApplicationCategory.CORE_SYSTEM,
                is_apple=True,
                is_user_app=False,
            ),
            MacAppInfo(
                name="Google Chrome",
                bundle_id="com.google.Chrome",
                bundle_path="/Applications/Google Chrome.app",
                version="157.0.8103.51",
                build_version="8103.51",
                executable_name="Google Chrome",
                executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                min_os_version="10.15.0",
                ownership=ComponentOwnership.VENDOR_MANAGED,
                category=ApplicationCategory.WEB_BROWSER,
                is_apple=False,
                is_user_app=True,
            ),
            MacAppInfo(
                name="Visual Studio Code",
                bundle_id="com.microsoft.VSCode",
                bundle_path="/Applications/Visual Studio Code.app",
                version="1.95.0",
                build_version="1.95.0",
                executable_name="Code",
                executable_path="/Applications/Visual Studio Code.app/Contents/MacOS/Code",
                min_os_version="10.15.0",
                ownership=ComponentOwnership.VENDOR_MANAGED,
                category=ApplicationCategory.DEVELOPER_TOOL,
                is_apple=False,
                is_user_app=True,
            ),
            MacAppInfo(
                name="Docker",
                bundle_id="com.docker.docker",
                bundle_path="/Applications/Docker.app",
                version="4.35.0",
                build_version="170884",
                executable_name="Docker Desktop",
                executable_path="/Applications/Docker.app/Contents/MacOS/Docker Desktop",
                min_os_version="11.0",
                ownership=ComponentOwnership.VENDOR_MANAGED,
                category=ApplicationCategory.DEVELOPER_TOOL,
                is_apple=False,
                is_user_app=True,
            ),
            MacAppInfo(
                name="CustomTool",
                bundle_id="com.user.CustomTool",
                bundle_path="/Users/mockuser/Applications/CustomTool.app",
                version="1.0.0",
                build_version="1",
                executable_name="CustomTool",
                executable_path="/Users/mockuser/Applications/CustomTool.app/Contents/MacOS/CustomTool",
                min_os_version="12.0",
                ownership=ComponentOwnership.USER_MANAGED,
                category=ApplicationCategory.UTILITY,
                is_apple=False,
                is_user_app=True,
            ),
        ]

        system_count = sum(1 for a in apps if a.ownership == ComponentOwnership.SYSTEM_MANAGED)
        vendor_count = sum(1 for a in apps if a.ownership == ComponentOwnership.VENDOR_MANAGED)
        user_count = sum(1 for a in apps if a.ownership == ComponentOwnership.USER_MANAGED)

        return MacAppInventoryReport(
            collection_method="MOCK_PLATFORM_ADAPTER",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            host_platform="macOS-Darwin-arm64-AppleSilicon-Mock",
            applications=apps,
            total_applications_count=len(apps),
            system_managed_count=system_count,
            vendor_managed_count=vendor_count,
            user_managed_count=user_count,
            warnings=[],
            unavailable_telemetry=[],
        )

    def detect(
        self,
        mock: bool = False,
        mock_adapter: Optional[Any] = None,
    ) -> MacAppInventoryReport:
        """Inspect installed macOS application bundles in read-only user space."""
        if mock or platform.system() != "Darwin":
            report = self.detect_mock(mock_adapter)
            if platform.system() != "Darwin":
                unavailable = list(report.unavailable_telemetry)
                unavailable.extend(["mdfind", "system_applications_volume"])
                return MacAppInventoryReport(
                    collection_method="MOCK_PLATFORM_ADAPTER",
                    timestamp=report.timestamp,
                    host_platform=f"{platform.system()}-{platform.machine()}",
                    applications=report.applications,
                    total_applications_count=report.total_applications_count,
                    system_managed_count=report.system_managed_count,
                    vendor_managed_count=report.vendor_managed_count,
                    user_managed_count=report.user_managed_count,
                    warnings=["Non-Darwin host platform; returning simulated Apple Silicon applications"],
                    unavailable_telemetry=unavailable,
                )
            return report

        apps = self.scan_directories()

        system_count = sum(1 for a in apps if a.ownership == ComponentOwnership.SYSTEM_MANAGED)
        vendor_count = sum(1 for a in apps if a.ownership == ComponentOwnership.VENDOR_MANAGED)
        user_count = sum(1 for a in apps if a.ownership == ComponentOwnership.USER_MANAGED)

        return MacAppInventoryReport(
            collection_method="NATIVE_DARWIN_BUNDLE_SCAN",
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            host_platform=f"{platform.system()}-{platform.machine()}",
            applications=apps,
            total_applications_count=len(apps),
            system_managed_count=system_count,
            vendor_managed_count=vendor_count,
            user_managed_count=user_count,
            warnings=[],
            unavailable_telemetry=[],
        )
