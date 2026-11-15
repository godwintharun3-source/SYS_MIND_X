"""Domain models and data contracts for application ownership classification and exclusion."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from system_mind.core.types import ComponentOwnership


class ApplicationType(str, Enum):
    """Classification of application categories."""

    SYSTEM_CORE = "SYSTEM_CORE"
    USER_DESKTOP_APP = "USER_DESKTOP_APP"
    DEVELOPER_TOOLCHAIN = "DEVELOPER_TOOLCHAIN"
    PROJECT_DEPENDENCY = "PROJECT_DEPENDENCY"
    USER_CLI_TOOL = "USER_CLI_TOOL"
    BACKGROUND_SERVICE = "BACKGROUND_SERVICE"


class InstallScope(str, Enum):
    """Scope of software installation location."""

    SYSTEM_WIDE = "SYSTEM_WIDE"
    USER_LOCAL = "USER_LOCAL"
    PROJECT_LOCAL = "PROJECT_LOCAL"


@dataclass(frozen=True)
class ApplicationProfile:
    """Detailed structural metadata and ownership profile of an application."""

    app_id: str
    display_name: str
    app_type: ApplicationType
    install_scope: InstallScope
    install_path: str
    executable_path: str
    ownership: ComponentOwnership
    managed_by: str
    is_excluded_from_autonomous_updates: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExclusionVerdict:
    """Outcome of evaluating an application or path against user-app exclusion rules."""

    target_path_or_id: str
    is_excluded: bool
    ownership: ComponentOwnership
    reason: str
    matching_rule: str
    override_permitted: bool = True
