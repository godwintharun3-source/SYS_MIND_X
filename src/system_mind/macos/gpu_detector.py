"""Read-only macOS GPU and display inventory telemetry detector."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import logging
from pathlib import Path
import platform
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from system_mind.macos.gpu_models import (
    DisplayConnectionType,
    GpuBusType,
    MacDisplayInfo,
    MacGpuInfo,
    MacGpuReport,
)

logger = logging.getLogger(__name__)

_DISPLAY_SALT = "sysmind-display-salt:"


class MacGpuDetector:
    """Read-only, passive introspection engine for macOS GPUs and connected visual displays."""

    def __init__(self, salt: str = _DISPLAY_SALT) -> None:
        self._salt = salt

    def anonymize_serial(self, raw_serial: Optional[str]) -> Optional[str]:
        """Anonymize hardware display serial numbers using a salted SHA-256 digest (INV-GPU-02)."""
        if not raw_serial or not str(raw_serial).strip():
            return None
        clean_serial = str(raw_serial).strip().lower()
        digest = hashlib.sha256(f"{self._salt}{clean_serial}".encode("utf-8")).hexdigest()[:16]
        return f"sha256:{digest}"

    def classify_bus(self, raw_bus: Optional[str]) -> GpuBusType:
        """Classify GPU interconnect bus architecture into GpuBusType."""
        if not raw_bus:
            return GpuBusType.UNKNOWN
        bus_lower = raw_bus.lower()
        if "builtin" in bus_lower or "built-in" in bus_lower or "integrated" in bus_lower:
            return GpuBusType.BUILTIN
        elif "pcie" in bus_lower or "pci" in bus_lower or "egpu" in bus_lower:
            return GpuBusType.PCIE
        return GpuBusType.UNKNOWN

    def classify_connection(
        self,
        raw_conn: Optional[str],
        display_type: Optional[str] = None,
    ) -> DisplayConnectionType:
        """Classify physical or virtual display connection type into DisplayConnectionType."""
        conn_lower = (raw_conn or "").lower()
        type_lower = (display_type or "").lower()

        if "internal" in conn_lower or "built-in" in type_lower or "retinalcd" in conn_lower:
            return DisplayConnectionType.INTERNAL
        elif "displayport" in conn_lower:
            return DisplayConnectionType.DISPLAYPORT
        elif "hdmi" in conn_lower:
            return DisplayConnectionType.HDMI
        elif "thunderbolt" in conn_lower:
            return DisplayConnectionType.THUNDERBOLT
        elif "airplay" in conn_lower or "sidecar" in conn_lower:
            return DisplayConnectionType.AIRPLAY
        return DisplayConnectionType.UNKNOWN

    def parse_refresh_rate(
        self,
        resolution_str: Optional[str],
    ) -> Tuple[Optional[str], Optional[float]]:
        """Parse resolution string into UI resolution and refresh rate in Hz."""
        if not resolution_str:
            return None, None
        match = re.match(r"^(.*?)\s*@\s*([\d\.]+)\s*Hz", resolution_str.strip())
        if match:
            ui_res = match.group(1).strip()
            try:
                rate = float(match.group(2))
                return ui_res, rate
            except ValueError:
                return ui_res, None
        return resolution_str.strip(), None

    def parse_spdisplays_json(
        self,
        data: Dict[str, Any],
    ) -> Tuple[List[MacGpuInfo], List[str]]:
        """Parse dictionary output from unprivileged `system_profiler SPDisplaysDataType -json`."""
        gpus: List[MacGpuInfo] = []
        warnings: List[str] = []

        raw_items = data.get("SPDisplaysDataType", [])
        if not isinstance(raw_items, list):
            warnings.append("SPDisplaysDataType root element is not a JSON list")
            return gpus, warnings

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            name = item.get("sppci_model") or item.get("_name") or "Unknown GPU"
            vendor_raw = item.get("spdisplays_vendor", "Apple")
            vendor = "Apple" if "apple" in vendor_raw.lower() else vendor_raw

            core_count = None
            if "sppci_cores" in item:
                try:
                    core_count = int(str(item["sppci_cores"]).strip())
                except (ValueError, TypeError):
                    core_count = None

            bus_type = self.classify_bus(item.get("sppci_bus"))
            metal_support = item.get("spdisplays_mtlgpufamilysupport")
            device_type = item.get("sppci_device_type", "spdisplays_gpu")

            vram_text = item.get("spdisplays_vram") or item.get("spdisplays_vram_shared")
            if not vram_text and bus_type == GpuBusType.BUILTIN and vendor == "Apple":
                vram_text = "Unified Memory"

            displays: List[MacDisplayInfo] = []
            ndrvs = item.get("spdisplays_ndrvs", [])
            if isinstance(ndrvs, list):
                for d in ndrvs:
                    if not isinstance(d, dict):
                        continue
                    d_name = d.get("_name", "Display")
                    display_id = str(d.get("_spdisplays_displayID")) if d.get("_spdisplays_displayID") is not None else None
                    vendor_id = str(d.get("_spdisplays_display-vendor-id")) if d.get("_spdisplays_display-vendor-id") is not None else None
                    product_id = str(d.get("_spdisplays_display-product-id")) if d.get("_spdisplays_display-product-id") is not None else None
                    raw_serial = d.get("_spdisplays_display-serial-number")
                    anonymized_serial = self.anonymize_serial(raw_serial)

                    native_pixels = d.get("_spdisplays_pixels")
                    resolution = d.get("_spdisplays_resolution")
                    ui_res, refresh_rate = self.parse_refresh_rate(resolution)

                    conn_type = self.classify_connection(
                        d.get("spdisplays_connection_type"),
                        d.get("spdisplays_display_type"),
                    )

                    is_main = d.get("spdisplays_main") == "spdisplays_yes"
                    display_type_str = d.get("spdisplays_display_type", "")
                    pixel_res_str = d.get("spdisplays_pixelresolution", "")
                    is_builtin = (
                        conn_type == DisplayConnectionType.INTERNAL
                        or "built-in" in display_type_str.lower()
                    )
                    is_online = d.get("spdisplays_online") == "spdisplays_yes" if "spdisplays_online" in d else True
                    is_mirror = d.get("spdisplays_mirror") != "spdisplays_off" if "spdisplays_mirror" in d else False

                    pixel_density_retina = (
                        "retina" in display_type_str.lower()
                        or "retina" in pixel_res_str.lower()
                    )
                    ambient_brightness = d.get("spdisplays_ambient_brightness") == "spdisplays_yes"

                    displays.append(
                        MacDisplayInfo(
                            name=d_name,
                            display_id=display_id,
                            vendor_id=vendor_id,
                            product_id=product_id,
                            anonymized_serial_hash=anonymized_serial,
                            native_pixels=native_pixels,
                            resolution=resolution,
                            ui_resolution=ui_res,
                            refresh_rate_hz=refresh_rate,
                            is_main=is_main,
                            is_builtin=is_builtin,
                            is_online=is_online,
                            is_mirror=is_mirror,
                            connection_type=conn_type,
                            pixel_density_retina=pixel_density_retina,
                            ambient_brightness=ambient_brightness,
                        )
                    )

            gpus.append(
                MacGpuInfo(
                    name=name,
                    vendor=vendor,
                    core_count=core_count,
                    bus_type=bus_type,
                    metal_support=metal_support,
                    device_type=device_type,
                    vram_text=vram_text,
                    displays=displays,
                )
            )

        return gpus, warnings

    def detect_mock(self, mock_adapter: Optional[Any] = None) -> MacGpuReport:
        """Construct deterministic Apple Silicon GPU and display telemetry mock (INV-GPU-04)."""
        display = MacDisplayInfo(
            name="Color LCD",
            display_id="1",
            vendor_id="610",
            product_id="a045",
            anonymized_serial_hash=self.anonymize_serial("MOCK-DISPLAY-APPLE-SILICON-2026"),
            native_pixels="2880 x 1800",
            resolution="1440 x 900 @ 60.00Hz",
            ui_resolution="1440 x 900",
            refresh_rate_hz=60.0,
            is_main=True,
            is_builtin=True,
            is_online=True,
            is_mirror=False,
            connection_type=DisplayConnectionType.INTERNAL,
            pixel_density_retina=True,
            ambient_brightness=True,
        )

        gpu = MacGpuInfo(
            name="Apple M1",
            vendor="Apple",
            core_count=8,
            bus_type=GpuBusType.BUILTIN,
            metal_support="spdisplays_metal4",
            device_type="spdisplays_gpu",
            vram_text="Unified Memory",
            displays=[display],
        )

        return MacGpuReport(
            gpus=[gpu],
            total_gpu_count=1,
            total_display_count=1,
            primary_display_resolution="1440 x 900 @ 60.00Hz",
            has_builtin_display=True,
            has_external_display=False,
            collected_at_epoch_secs=time.time(),
            collection_method="MOCK_PLATFORM_ADAPTER",
            unavailable_telemetry=[],
            warnings=[],
        )

    def detect(
        self,
        use_mock: bool = False,
        mock_adapter: Optional[Any] = None,
    ) -> MacGpuReport:
        """Perform read-only query of macOS GPU and display inventory with unprivileged tools."""
        if use_mock:
            return self.detect_mock(mock_adapter)

        if platform.system() != "Darwin":
            logger.info("Non-Darwin platform detected; falling back to mock platform adapter")
            report = self.detect_mock(mock_adapter)
            return replace(
                report,
                collection_method="NON_DARWIN_MOCK_FALLBACK",
                unavailable_telemetry=["system_profiler SPDisplaysDataType requires Darwin macOS host"],
            )

        unavailable: List[str] = []
        warnings: List[str] = []

        try:
            cmd = ["/usr/sbin/system_profiler", "SPDisplaysDataType", "-json"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode != 0:
                warnings.append(f"system_profiler SPDisplaysDataType exited with code {proc.returncode}")
                return self.detect_mock(mock_adapter)

            data = json.loads(proc.stdout)
            gpus, parse_warnings = self.parse_spdisplays_json(data)
            warnings.extend(parse_warnings)

            total_displays = sum(len(g.displays) for g in gpus)
            has_builtin = any(d.is_builtin for g in gpus for d in g.displays)
            has_external = any(not d.is_builtin for g in gpus for d in g.displays)

            primary_res = None
            for g in gpus:
                for d in g.displays:
                    if d.is_main:
                        primary_res = d.resolution
                        break
                if primary_res:
                    break

            return MacGpuReport(
                gpus=gpus,
                total_gpu_count=len(gpus),
                total_display_count=total_displays,
                primary_display_resolution=primary_res,
                has_builtin_display=has_builtin,
                has_external_display=has_external,
                collected_at_epoch_secs=time.time(),
                collection_method="NATIVE_DARWIN_SYSTEM_PROFILER",
                unavailable_telemetry=unavailable,
                warnings=warnings,
            )

        except subprocess.TimeoutExpired:
            warnings.append("system_profiler SPDisplaysDataType query timed out after 10s")
            return self.detect_mock(mock_adapter)
        except Exception as exc:
            warnings.append(f"GPU detection exception: {str(exc)}")
            return self.detect_mock(mock_adapter)
