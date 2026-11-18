"""Database repository for Hardware, OS Kernel, and Application digital twin entities."""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from system_mind.core.types import ComponentOwnership
from system_mind.database.entity_models import (
    ApplicationEntityRecord,
    HardwareCategory,
    HardwareEntityRecord,
    OsKernelEntityRecord,
)


class EntityRepository:
    """Manages transactional CRUD operations and indexed queries for digital twin database entities."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ==========================================
    # Hardware Entities
    # ==========================================

    def save_hardware_entity(self, record: HardwareEntityRecord) -> None:
        """Insert or replace a hardware entity record."""
        sql = """
            INSERT OR REPLACE INTO hardware_entities (
                entity_urn, device_id, category, model_name, vendor,
                serial_hash, attributes_json, observed_at, provenance_source,
                scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(sql, record.to_db_row())

    def get_hardware_entity(self, entity_urn: str) -> Optional[HardwareEntityRecord]:
        """Fetch a single hardware entity by its canonical URN."""
        cursor = self.conn.execute(
            """
            SELECT entity_urn, device_id, category, model_name, vendor,
                   serial_hash, attributes_json, observed_at, provenance_source,
                   scan_proves_safe
            FROM hardware_entities
            WHERE entity_urn = ?;
            """,
            (entity_urn,),
        )
        row = cursor.fetchone()
        return HardwareEntityRecord.from_db_row(row) if row else None

    def list_hardware_entities(
        self,
        device_id: Optional[str] = None,
        category: Optional[HardwareCategory] = None,
    ) -> List[HardwareEntityRecord]:
        """Query hardware entities with optional filtering by device_id and category."""
        conditions = []
        params = []

        if device_id is not None:
            conditions.append("device_id = ?")
            params.append(device_id)

        if category is not None:
            conditions.append("category = ?")
            params.append(category.value)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT entity_urn, device_id, category, model_name, vendor,
                   serial_hash, attributes_json, observed_at, provenance_source,
                   scan_proves_safe
            FROM hardware_entities
            {where_clause}
            ORDER BY observed_at DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        return [HardwareEntityRecord.from_db_row(row) for row in cursor.fetchall()]

    def delete_hardware_entity(self, entity_urn: str) -> bool:
        """Delete a hardware entity by URN. Returns True if row was deleted."""
        cursor = self.conn.execute(
            "DELETE FROM hardware_entities WHERE entity_urn = ?;",
            (entity_urn,),
        )
        return cursor.rowcount > 0

    # ==========================================
    # OS Kernel Entities
    # ==========================================

    def save_os_kernel_entity(self, record: OsKernelEntityRecord) -> None:
        """Insert or replace an OS kernel entity record."""
        sql = """
            INSERT OR REPLACE INTO os_kernel_entities (
                entity_urn, device_id, os_family, product_version, build_version,
                kernel_release, architecture, security_posture_json, observed_at,
                provenance_source, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(sql, record.to_db_row())

    def get_os_kernel_entity(self, entity_urn: str) -> Optional[OsKernelEntityRecord]:
        """Fetch an OS kernel entity by its canonical URN."""
        cursor = self.conn.execute(
            """
            SELECT entity_urn, device_id, os_family, product_version, build_version,
                   kernel_release, architecture, security_posture_json, observed_at,
                   provenance_source, scan_proves_safe
            FROM os_kernel_entities
            WHERE entity_urn = ?;
            """,
            (entity_urn,),
        )
        row = cursor.fetchone()
        return OsKernelEntityRecord.from_db_row(row) if row else None

    def list_os_kernel_entities(
        self,
        device_id: Optional[str] = None,
    ) -> List[OsKernelEntityRecord]:
        """Query OS kernel entities with optional filtering by device_id."""
        if device_id is not None:
            cursor = self.conn.execute(
                """
                SELECT entity_urn, device_id, os_family, product_version, build_version,
                       kernel_release, architecture, security_posture_json, observed_at,
                       provenance_source, scan_proves_safe
                FROM os_kernel_entities
                WHERE device_id = ?
                ORDER BY observed_at DESC;
                """,
                (device_id,),
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT entity_urn, device_id, os_family, product_version, build_version,
                       kernel_release, architecture, security_posture_json, observed_at,
                       provenance_source, scan_proves_safe
                FROM os_kernel_entities
                ORDER BY observed_at DESC;
                """
            )
        return [OsKernelEntityRecord.from_db_row(row) for row in cursor.fetchall()]

    def delete_os_kernel_entity(self, entity_urn: str) -> bool:
        """Delete an OS kernel entity by URN. Returns True if row was deleted."""
        cursor = self.conn.execute(
            "DELETE FROM os_kernel_entities WHERE entity_urn = ?;",
            (entity_urn,),
        )
        return cursor.rowcount > 0

    # ==========================================
    # Application Entities
    # ==========================================

    def save_application_entity(self, record: ApplicationEntityRecord) -> None:
        """Insert or replace an application entity record."""
        sql = """
            INSERT OR REPLACE INTO application_entities (
                entity_urn, device_id, bundle_id, app_name, version,
                install_path, ownership, code_signature_json, observed_at,
                provenance_source, scan_proves_safe
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        self.conn.execute(sql, record.to_db_row())

    def get_application_entity(self, entity_urn: str) -> Optional[ApplicationEntityRecord]:
        """Fetch an application entity by its canonical URN."""
        cursor = self.conn.execute(
            """
            SELECT entity_urn, device_id, bundle_id, app_name, version,
                   install_path, ownership, code_signature_json, observed_at,
                   provenance_source, scan_proves_safe
            FROM application_entities
            WHERE entity_urn = ?;
            """,
            (entity_urn,),
        )
        row = cursor.fetchone()
        return ApplicationEntityRecord.from_db_row(row) if row else None

    def list_application_entities(
        self,
        device_id: Optional[str] = None,
        ownership: Optional[ComponentOwnership] = None,
    ) -> List[ApplicationEntityRecord]:
        """Query application entities with optional filtering by device_id and component ownership."""
        conditions = []
        params = []

        if device_id is not None:
            conditions.append("device_id = ?")
            params.append(device_id)

        if ownership is not None:
            conditions.append("ownership = ?")
            params.append(ownership.value)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        sql = f"""
            SELECT entity_urn, device_id, bundle_id, app_name, version,
                   install_path, ownership, code_signature_json, observed_at,
                   provenance_source, scan_proves_safe
            FROM application_entities
            {where_clause}
            ORDER BY observed_at DESC;
        """
        cursor = self.conn.execute(sql, tuple(params))
        return [ApplicationEntityRecord.from_db_row(row) for row in cursor.fetchall()]

    def delete_application_entity(self, entity_urn: str) -> bool:
        """Delete an application entity by URN. Returns True if row was deleted."""
        cursor = self.conn.execute(
            "DELETE FROM application_entities WHERE entity_urn = ?;",
            (entity_urn,),
        )
        return cursor.rowcount > 0

    # ==========================================
    # Entity Counts & Aggregations
    # ==========================================

    def count_entities(self, device_id: Optional[str] = None) -> Dict[str, int]:
        """Count total entities per category."""
        if device_id is not None:
            hw = self.conn.execute(
                "SELECT COUNT(*) FROM hardware_entities WHERE device_id = ?;", (device_id,)
            ).fetchone()[0]
            os_cnt = self.conn.execute(
                "SELECT COUNT(*) FROM os_kernel_entities WHERE device_id = ?;", (device_id,)
            ).fetchone()[0]
            app_cnt = self.conn.execute(
                "SELECT COUNT(*) FROM application_entities WHERE device_id = ?;", (device_id,)
            ).fetchone()[0]
        else:
            hw = self.conn.execute("SELECT COUNT(*) FROM hardware_entities;").fetchone()[0]
            os_cnt = self.conn.execute("SELECT COUNT(*) FROM os_kernel_entities;").fetchone()[0]
            app_cnt = self.conn.execute("SELECT COUNT(*) FROM application_entities;").fetchone()[0]

        return {
            "hardware": hw,
            "os_kernel": os_cnt,
            "applications": app_cnt,
            "total": hw + os_cnt + app_cnt,
        }
