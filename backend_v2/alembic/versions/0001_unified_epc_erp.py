"""Unified EPC ERP baseline schema for DocumentRecord, AuditEvent, DispatchReservation, PoRevision, ITP Baseline, and ConcessionWaiver.

Revision ID: 0001_unified_epc_erp
Revises: 
Create Date: 2026-11-22 09:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001_unified_epc_erp"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tables = _existing_tables()

    if "document_registry" not in tables:
        op.create_table(
            "document_registry",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("bucket", sa.String(length=64), nullable=False),
            sa.Column("rel_path", sa.String(length=512), nullable=False),
            sa.Column("original_filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=128), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256_hash", sa.String(length=64), nullable=False),
            sa.Column("po_number", sa.String(length=64), nullable=True),
            sa.Column("inspection_id", sa.String(length=64), nullable=True),
            sa.Column("classification", sa.String(length=64), nullable=False),
            sa.Column("uploaded_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_document_registry_bucket", "document_registry", ["bucket"])
        op.create_index("ix_document_registry_sha256_hash", "document_registry", ["sha256_hash"])
        op.create_index("ix_document_registry_po_number", "document_registry", ["po_number"])
        op.create_index("ix_document_registry_inspection_id", "document_registry", ["inspection_id"])

    if "audit_events" not in tables:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("entity_type", sa.String(length=64), nullable=False),
            sa.Column("entity_id", sa.String(length=128), nullable=False),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("actor_id", sa.String(length=64), nullable=True),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("actor_role", sa.String(length=64), nullable=True),
            sa.Column("before_json", sa.Text(), nullable=True),
            sa.Column("after_json", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_audit_events_entity_type", "audit_events", ["entity_type"])
        op.create_index("ix_audit_events_entity_id", "audit_events", ["entity_id"])
        op.create_index("ix_audit_events_action", "audit_events", ["action"])
        op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    if "epc_dispatch_reservations" not in tables:
        op.create_table(
            "epc_dispatch_reservations",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("po_number", sa.String(length=64), nullable=False),
            sa.Column("item_id", sa.String(length=64), nullable=False),
            sa.Column("irc_number", sa.String(length=64), nullable=True),
            sa.Column("reserved_qty", sa.Float(), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_epc_dispatch_reservations_po_number", "epc_dispatch_reservations", ["po_number"])
        op.create_index("ix_epc_dispatch_reservations_item_id", "epc_dispatch_reservations", ["item_id"])
        op.create_index("ix_epc_dispatch_reservations_status", "epc_dispatch_reservations", ["status"])
        op.create_index("ix_dispatch_po_item", "epc_dispatch_reservations", ["po_number", "item_id"])

    if "epc_po_revisions" not in tables:
        op.create_table(
            "epc_po_revisions",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("po_number", sa.String(length=64), nullable=False),
            sa.Column("revision_no", sa.String(length=16), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("new_delivery_date", sa.String(length=32), nullable=True),
            sa.Column("eot_days", sa.Integer(), nullable=False),
            sa.Column("line_deltas_json", sa.Text(), nullable=False),
            sa.Column("approved_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_epc_po_revisions_po_number", "epc_po_revisions", ["po_number"])

    if "epc_itp_documents" not in tables:
        op.create_table(
            "epc_itp_documents",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("po_number", sa.String(length=64), nullable=False),
            sa.Column("doc_no", sa.String(length=128), nullable=False),
            sa.Column("revision", sa.String(length=32), nullable=False),
            sa.Column("approval_code", sa.String(length=32), nullable=False),
            sa.Column("source_document_id", sa.String(length=64), nullable=True),
            sa.Column("sha256_hash", sa.String(length=64), nullable=True),
            sa.Column("scope_mode", sa.String(length=32), nullable=False),
            sa.Column("scoped_items_json", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("verified_by", sa.String(length=255), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_epc_itp_documents_po_number", "epc_itp_documents", ["po_number"])
        op.create_index("ix_epc_itp_documents_status", "epc_itp_documents", ["status"])

    if "epc_itp_steps" not in tables:
        op.create_table(
            "epc_itp_steps",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column(
                "itp_document_id",
                sa.String(length=64),
                sa.ForeignKey("epc_itp_documents.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("step_no", sa.String(length=32), nullable=False),
            sa.Column("phase", sa.String(length=128), nullable=True),
            sa.Column("activity_description", sa.Text(), nullable=False),
            sa.Column("reference_spec", sa.String(length=255), nullable=True),
            sa.Column("acceptance_criteria", sa.Text(), nullable=True),
            sa.Column("verifying_document", sa.String(length=255), nullable=True),
            sa.Column("vendor_point", sa.String(length=16), nullable=False),
            sa.Column("subvendor_point", sa.String(length=16), nullable=False),
            sa.Column("contractor_tpi_point", sa.String(length=16), nullable=False),
            sa.Column("company_tpa_point", sa.String(length=16), nullable=False),
            sa.Column("source_page_no", sa.Integer(), nullable=False),
            sa.Column("confidence", sa.String(length=16), nullable=False),
            sa.Column("execution_status", sa.String(length=32), nullable=False),
            sa.Column("waiver_ref", sa.String(length=128), nullable=True),
            sa.Column("waiver_doc_id", sa.String(length=64), nullable=True),
            sa.Column("linked_inspection_id", sa.String(length=64), nullable=True),
            sa.Column("is_hold_point", sa.Boolean(), nullable=False),
        )
        op.create_index("ix_epc_itp_steps_itp_document_id", "epc_itp_steps", ["itp_document_id"])

    if "epc_concessions_waivers" not in tables:
        op.create_table(
            "epc_concessions_waivers",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("po_number", sa.String(length=64), nullable=False),
            sa.Column("waiver_type", sa.String(length=32), nullable=False),
            sa.Column("target_ref_id", sa.String(length=128), nullable=False),
            sa.Column("concession_ref_no", sa.String(length=128), nullable=False),
            sa.Column("justification", sa.Text(), nullable=False),
            sa.Column("approved_by_name", sa.String(length=255), nullable=False),
            sa.Column("approved_by_role", sa.String(length=64), nullable=False),
            sa.Column("attachment_doc_id", sa.String(length=64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_epc_concessions_waivers_po_number", "epc_concessions_waivers", ["po_number"])
        op.create_index("ix_epc_concessions_waivers_target_ref_id", "epc_concessions_waivers", ["target_ref_id"])


def downgrade() -> None:
    for tbl in (
        "epc_concessions_waivers",
        "epc_itp_steps",
        "epc_itp_documents",
        "epc_po_revisions",
        "epc_dispatch_reservations",
        "audit_events",
        "document_registry",
    ):
        if tbl in _existing_tables():
            op.drop_table(tbl)
