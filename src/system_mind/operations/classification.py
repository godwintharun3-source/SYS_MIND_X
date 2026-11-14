"""Typed operation taxonomy, risk tiers, privilege levels, and reversibility classification."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from system_mind.core.charter import CharterValidator
from system_mind.core.types import (
    ActionContract,
    ApprovalRequirement,
    ComponentOwnership,
    OperationRiskTier,
    Reversibility,
)


class PrivilegeLevel(str, Enum):
    """Execution context and administrative privilege classification."""

    UNPRIVILEGED_USER = "UNPRIVILEGED_USER"
    USER_CONSENT_GRANTED = "USER_CONSENT_GRANTED"
    ELEVATED_BROKER_REQUIRED = "ELEVATED_BROKER_REQUIRED"
    HARDWARE_FIRMWARE_ENTITLED = "HARDWARE_FIRMWARE_ENTITLED"


class RollbackStrategy(str, Enum):
    """Deterministic compensation and recovery strategies."""

    ATOMIC_FILE_RESTORE = "ATOMIC_FILE_RESTORE"
    STATE_INVERSE_ACTION = "STATE_INVERSE_ACTION"
    TRANSACTIONAL_SNAPSHOT = "TRANSACTIONAL_SNAPSHOT"
    NOT_REVERSIBLE_COMPENSATION_ONLY = "NOT_REVERSIBLE_COMPENSATION_ONLY"
    NONE = "NONE"


@dataclass(frozen=True)
class SystemOperationDefinition:
    """Formal specification of a system operation across impact, privilege, and reversibility."""

    operation_id: str
    name: str
    category: str
    target_ownership: ComponentOwnership
    risk_tier: OperationRiskTier
    privilege_level: PrivilegeLevel
    reversibility: Reversibility
    rollback_strategy: RollbackStrategy
    default_approval: ApprovalRequirement
    can_run_autonomously: bool
    required_preconditions: List[str]
    expected_postconditions: List[str]
    description: str


@dataclass
class OperationClassificationResult:
    """Outcome of operation classification and policy audit."""

    is_valid: bool
    operation: Optional[SystemOperationDefinition] = None
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class OperationCatalogRegistry:
    """Standard verified catalog of platform operations and their governance profiles."""

    _OPERATIONS: Dict[str, SystemOperationDefinition] = {
        "OP-DIAG-01": SystemOperationDefinition(
            operation_id="OP-DIAG-01",
            name="Read System Telemetry & Hardware Sensors",
            category="Diagnostics",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.READ_ONLY,
            privilege_level=PrivilegeLevel.UNPRIVILEGED_USER,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.NONE,
            default_approval=ApprovalRequirement.NONE,
            can_run_autonomously=True,
            required_preconditions=["host_reachable"],
            expected_postconditions=["telemetry_recorded"],
            description="Inspect system load, memory, thermal metrics, and storage stats.",
        ),
        "OP-DIAG-02": SystemOperationDefinition(
            operation_id="OP-DIAG-02",
            name="Inspect Process Table and Sockets",
            category="Diagnostics",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.READ_ONLY,
            privilege_level=PrivilegeLevel.UNPRIVILEGED_USER,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.NONE,
            default_approval=ApprovalRequirement.NONE,
            can_run_autonomously=True,
            required_preconditions=["procfs_or_sysctl_available"],
            expected_postconditions=["processes_listed"],
            description="Query active user processes and open listening ports without modification.",
        ),
        "OP-MAINT-01": SystemOperationDefinition(
            operation_id="OP-MAINT-01",
            name="Vacuum Temporary Caches",
            category="Maintenance",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.LOW_IMPACT,
            privilege_level=PrivilegeLevel.UNPRIVILEGED_USER,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.ATOMIC_FILE_RESTORE,
            default_approval=ApprovalRequirement.NONE,
            can_run_autonomously=True,
            required_preconditions=["cache_dir_exists", "disk_writable"],
            expected_postconditions=["cache_cleared"],
            description="Remove stale temporary files under designated system cache directories.",
        ),
        "OP-MAINT-02": SystemOperationDefinition(
            operation_id="OP-MAINT-02",
            name="Rotate System and Service Logs",
            category="Maintenance",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.LOW_IMPACT,
            privilege_level=PrivilegeLevel.ELEVATED_BROKER_REQUIRED,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.ATOMIC_FILE_RESTORE,
            default_approval=ApprovalRequirement.NONE,
            can_run_autonomously=True,
            required_preconditions=["log_dir_exists", "broker_active"],
            expected_postconditions=["logs_compressed_and_rotated"],
            description="Archive and compress rotated log files to conserve disk volume.",
        ),
        "OP-MAINT-03": SystemOperationDefinition(
            operation_id="OP-MAINT-03",
            name="Restart Background System Daemon",
            category="Maintenance",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.MEDIUM_IMPACT,
            privilege_level=PrivilegeLevel.ELEVATED_BROKER_REQUIRED,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.STATE_INVERSE_ACTION,
            default_approval=ApprovalRequirement.USER_EXPLICIT,
            can_run_autonomously=True,
            required_preconditions=["daemon_registered", "broker_active"],
            expected_postconditions=["daemon_running_fresh"],
            description="Restart a misbehaving or stalled system service daemon via broker.",
        ),
        "OP-MAINT-04": SystemOperationDefinition(
            operation_id="OP-MAINT-04",
            name="Vacuum systemd Journal Database",
            category="Maintenance",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.LOW_IMPACT,
            privilege_level=PrivilegeLevel.ELEVATED_BROKER_REQUIRED,
            reversibility=Reversibility.IRREVERSIBLE,
            rollback_strategy=RollbackStrategy.NOT_REVERSIBLE_COMPENSATION_ONLY,
            default_approval=ApprovalRequirement.NONE,
            can_run_autonomously=True,
            required_preconditions=["journalctl_available", "broker_active"],
            expected_postconditions=["journal_vacuumed"],
            description="Prune old systemd journal entries past retention threshold.",
        ),
        "OP-SEC-01": SystemOperationDefinition(
            operation_id="OP-SEC-01",
            name="Update OS Security Definitions & Threat Signatures",
            category="Security",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.LOW_IMPACT,
            privilege_level=PrivilegeLevel.ELEVATED_BROKER_REQUIRED,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.TRANSACTIONAL_SNAPSHOT,
            default_approval=ApprovalRequirement.NONE,
            can_run_autonomously=True,
            required_preconditions=["network_connected", "signature_valid"],
            expected_postconditions=["signatures_updated"],
            description="Fetch verified, vendor-signed threat signatures for OS defense.",
        ),
        "OP-SEC-02": SystemOperationDefinition(
            operation_id="OP-SEC-02",
            name="Execute External File in Disposable Isolation",
            category="Security",
            target_ownership=ComponentOwnership.VENDOR_MANAGED,
            risk_tier=OperationRiskTier.READ_ONLY,
            privilege_level=PrivilegeLevel.UNPRIVILEGED_USER,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.TRANSACTIONAL_SNAPSHOT,
            default_approval=ApprovalRequirement.USER_EXPLICIT,
            can_run_autonomously=False,
            required_preconditions=["file_staged_in_sandbox", "isolation_vm_active"],
            expected_postconditions=["execution_traced_isolated"],
            description="Zero-trust inspection and detonation of untrusted binary within disposable VM.",
        ),
        "OP-SYS-01": SystemOperationDefinition(
            operation_id="OP-SYS-01",
            name="Modify System Firewall Packet Filter Rules",
            category="System Configuration",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.HIGH_IMPACT,
            privilege_level=PrivilegeLevel.ELEVATED_BROKER_REQUIRED,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.STATE_INVERSE_ACTION,
            default_approval=ApprovalRequirement.USER_EXPLICIT,
            can_run_autonomously=False,
            required_preconditions=["firewall_daemon_active", "rule_schema_valid"],
            expected_postconditions=["rule_applied_verified"],
            description="Alter native OS packet filtering (pf, nftables, Windows Filtering Platform).",
        ),
        "OP-SYS-03": SystemOperationDefinition(
            operation_id="OP-SYS-03",
            name="Reinitialize Network Routing & Flush DNS Resolver",
            category="System Configuration",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.MEDIUM_IMPACT,
            privilege_level=PrivilegeLevel.ELEVATED_BROKER_REQUIRED,
            reversibility=Reversibility.PARTIALLY_REVERSIBLE,
            rollback_strategy=RollbackStrategy.STATE_INVERSE_ACTION,
            default_approval=ApprovalRequirement.USER_EXPLICIT,
            can_run_autonomously=False,
            required_preconditions=["network_adapter_detected", "broker_active"],
            expected_postconditions=["dns_flushed", "default_gateway_reconnected"],
            description="Flush resolver cache and reapply routing table; transient open sockets cannot be reverted.",
        ),
        "OP-SYS-02": SystemOperationDefinition(
            operation_id="OP-SYS-02",
            name="Apply Operating System Core Update",
            category="System Configuration",
            target_ownership=ComponentOwnership.SYSTEM_MANAGED,
            risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
            privilege_level=PrivilegeLevel.ELEVATED_BROKER_REQUIRED,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.TRANSACTIONAL_SNAPSHOT,
            default_approval=ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS,
            can_run_autonomously=False,
            required_preconditions=["ac_power_connected", "pre_update_snapshot_verified"],
            expected_postconditions=["os_reboot_pending_or_updated"],
            description="Install certified vendor operating system kernel and base updates.",
        ),
        "OP-HW-01": SystemOperationDefinition(
            operation_id="OP-HW-01",
            name="Query EFI / NVRAM Firmware Variables",
            category="Hardware & Firmware",
            target_ownership=ComponentOwnership.VENDOR_MANAGED,
            risk_tier=OperationRiskTier.READ_ONLY,
            privilege_level=PrivilegeLevel.HARDWARE_FIRMWARE_ENTITLED,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.NONE,
            default_approval=ApprovalRequirement.USER_EXPLICIT,
            can_run_autonomously=False,
            required_preconditions=["hardware_tpm_or_secure_boot_queryable"],
            expected_postconditions=["firmware_state_read"],
            description="Read platform firmware state and boot security configuration.",
        ),
        "OP-HW-02": SystemOperationDefinition(
            operation_id="OP-HW-02",
            name="Partition Map Alteration or Firmware Flash",
            category="Hardware & Firmware",
            target_ownership=ComponentOwnership.VENDOR_MANAGED,
            risk_tier=OperationRiskTier.CRITICAL_PRIVILEGED,
            privilege_level=PrivilegeLevel.HARDWARE_FIRMWARE_ENTITLED,
            reversibility=Reversibility.IRREVERSIBLE,
            rollback_strategy=RollbackStrategy.NOT_REVERSIBLE_COMPENSATION_ONLY,
            default_approval=ApprovalRequirement.TWO_PERSON_OR_BREAK_GLASS,
            can_run_autonomously=False,
            required_preconditions=["full_disk_backup_confirmed", "break_glass_verified"],
            expected_postconditions=["firmware_flashed_verified"],
            description="Destructive low-level disk repartitioning or firmware flashing.",
        ),
        "OP-USER-01": SystemOperationDefinition(
            operation_id="OP-USER-01",
            name="Update User Application",
            category="User Space",
            target_ownership=ComponentOwnership.USER_MANAGED,
            risk_tier=OperationRiskTier.LOW_IMPACT,
            privilege_level=PrivilegeLevel.USER_CONSENT_GRANTED,
            reversibility=Reversibility.REVERSIBLE,
            rollback_strategy=RollbackStrategy.TRANSACTIONAL_SNAPSHOT,
            default_approval=ApprovalRequirement.USER_EXPLICIT,
            can_run_autonomously=False,
            required_preconditions=["app_not_running", "user_consent_granted"],
            expected_postconditions=["app_updated_cleanly"],
            description="Update user productivity application with explicit user consent. Never autonomous.",
        ),
    }

    @classmethod
    def get(cls, operation_id: str) -> SystemOperationDefinition:
        """Retrieve operation definition by ID."""
        if operation_id not in cls._OPERATIONS:
            raise KeyError(f"Unknown operation ID: {operation_id}")
        return cls._OPERATIONS[operation_id]

    @classmethod
    def all_operations(cls) -> List[SystemOperationDefinition]:
        """Return all cataloged operation definitions."""
        return list(cls._OPERATIONS.values())

    @classmethod
    def filter_by_risk_tier(cls, risk_tier: OperationRiskTier) -> List[SystemOperationDefinition]:
        """Filter operations by risk tier."""
        return [op for op in cls._OPERATIONS.values() if op.risk_tier == risk_tier]

    @classmethod
    def filter_by_privilege_level(cls, privilege_level: PrivilegeLevel) -> List[SystemOperationDefinition]:
        """Filter operations by required privilege level."""
        return [op for op in cls._OPERATIONS.values() if op.privilege_level == privilege_level]

    @classmethod
    def filter_by_reversibility(cls, reversibility: Reversibility) -> List[SystemOperationDefinition]:
        """Filter operations by reversibility category."""
        return [op for op in cls._OPERATIONS.values() if op.reversibility == reversibility]

    @classmethod
    def get_autonomous_eligible_operations(cls) -> List[SystemOperationDefinition]:
        """Return all operations eligible for autonomous unattended maintenance."""
        return [op for op in cls._OPERATIONS.values() if op.can_run_autonomously]


class OperationClassifier:
    """Evaluates and validates actions against the operational taxonomy and governance rules."""

    @classmethod
    def classify_and_validate(
        cls,
        action: ActionContract,
        operation_id: Optional[str] = None,
    ) -> OperationClassificationResult:
        """Classify an action contract and validate invariants across impact, privilege, and reversibility."""
        violations: List[str] = []
        warnings: List[str] = []

        # 1. Base Charter Invariant Validation
        charter_res = CharterValidator.validate(action)
        if not charter_res.is_valid:
            violations.extend(charter_res.violations)

        # 2. Match catalog operation if provided
        op_def: Optional[SystemOperationDefinition] = None
        if operation_id:
            if operation_id not in OperationCatalogRegistry._OPERATIONS:
                violations.append(f"Catalog Violation: Unknown operation ID '{operation_id}'.")
            else:
                op_def = OperationCatalogRegistry.get(operation_id)
                # Verify that action properties conform to catalog definition
                if action.target_ownership != op_def.target_ownership:
                    violations.append(
                        f"Catalog Mismatch: Action target ownership '{action.target_ownership.value}' does not match operation catalog '{op_def.target_ownership.value}'."
                    )
                if action.risk_tier != op_def.risk_tier:
                    violations.append(
                        f"Catalog Mismatch: Action risk tier '{action.risk_tier.value}' does not match operation catalog '{op_def.risk_tier.value}'."
                    )

        # 3. Autonomous Maintenance Scope Invariant (Invariant 2)
        if action.is_autonomous_maintenance:
            if action.target_ownership != ComponentOwnership.SYSTEM_MANAGED:
                violations.append(
                    f"Operational Governance Violation: Autonomous maintenance is strictly limited to SYSTEM_MANAGED components. Target ownership '{action.target_ownership.value}' is forbidden."
                )
            if action.risk_tier not in (
                OperationRiskTier.READ_ONLY,
                OperationRiskTier.LOW_IMPACT,
                OperationRiskTier.MEDIUM_IMPACT,
            ):
                violations.append(
                    f"Operational Governance Violation: Autonomous maintenance cannot execute operations exceeding MEDIUM_IMPACT. Requested tier '{action.risk_tier.value}' is forbidden."
                )

        # 4. Reversibility & Rollback Plan Invariant
        if action.reversibility == Reversibility.REVERSIBLE:
            if not action.rollback_plan and (op_def and op_def.rollback_strategy == RollbackStrategy.NONE and action.risk_tier != OperationRiskTier.READ_ONLY):
                violations.append(
                    "Reversibility Invariant Violation: Mutating action claiming to be REVERSIBLE must provide a concrete rollback plan or strategy."
                )

        # 5. Critical Privileged Approval Invariant
        if action.risk_tier == OperationRiskTier.CRITICAL_PRIVILEGED:
            if action.approval_requirement == ApprovalRequirement.NONE:
                violations.append(
                    "Governance Violation: CRITICAL_PRIVILEGED operations cannot have ApprovalRequirement.NONE."
                )
            if not action.user_approved:
                violations.append(
                    "Governance Violation: CRITICAL_PRIVILEGED operations require explicit verified user authorization."
                )

        is_valid = (len(violations) == 0)
        return OperationClassificationResult(
            is_valid=is_valid,
            operation=op_def,
            violations=violations,
            warnings=warnings,
        )
