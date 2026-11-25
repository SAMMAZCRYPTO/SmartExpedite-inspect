"""Unified relational SQLAlchemy 2.0 models (SQLite local -> PostgreSQL / SQL Server ready)."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend_v2.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentRecord(Base):
    __tablename__ = "document_registry"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(64), index=True)
    rel_path: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256_hash: Mapped[str] = mapped_column(String(64), index=True)
    po_number: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    inspection_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    classification: Mapped[str] = mapped_column(String(64), default="general")
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class DispatchReservation(Base):
    __tablename__ = "epc_dispatch_reservations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    po_number: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    irc_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reserved_qty: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(64), default="AWAITING LOGISTICS MOVEMENT AUTHORITY", index=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_dispatch_po_item", "po_number", "item_id"),)


class PoRevision(Base):
    __tablename__ = "epc_po_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    po_number: Mapped[str] = mapped_column(String(64), index=True)
    revision_no: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_delivery_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    eot_days: Mapped[int] = mapped_column(Integer, default=0)
    line_deltas_json: Mapped[str] = mapped_column(Text, default="[]")
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ItpDocument(Base):
    __tablename__ = "epc_itp_documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    po_number: Mapped[str] = mapped_column(String(64), index=True)
    doc_no: Mapped[str] = mapped_column(String(128))
    revision: Mapped[str] = mapped_column(String(32), default="0")
    approval_code: Mapped[str] = mapped_column(String(32), default="Code 1")
    source_document_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sha256_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope_mode: Mapped[str] = mapped_column(String(32), default="WHOLE_PO")  # WHOLE_PO | ITEM_GROUP
    scoped_items_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT_EXTRACTED", index=True)  # DRAFT_EXTRACTED | LOCKED_ACTIVE | SUPERSEDED
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    steps: Mapped[list["ItpBaselineStep"]] = relationship(
        back_populates="itp_document", cascade="all, delete-orphan"
    )


class ItpBaselineStep(Base):
    __tablename__ = "epc_itp_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    itp_document_id: Mapped[str] = mapped_column(ForeignKey("epc_itp_documents.id", ondelete="CASCADE"), index=True)
    step_no: Mapped[str] = mapped_column(String(32))
    phase: Mapped[str | None] = mapped_column(String(128), nullable=True)
    activity_description: Mapped[str] = mapped_column(Text)
    reference_spec: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acceptance_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    verifying_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Exact 4-party EPC matrix across H, W, RW, R, M, -
    vendor_point: Mapped[str] = mapped_column(String(16), default="-")
    subvendor_point: Mapped[str] = mapped_column(String(16), default="-")
    contractor_tpi_point: Mapped[str] = mapped_column(String(16), default="-")
    company_tpa_point: Mapped[str] = mapped_column(String(16), default="-")
    source_page_no: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[str] = mapped_column(String(16), default="high")
    execution_status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING | VERIFIED_PASS | WAIVED | FAILED
    waiver_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    waiver_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    linked_inspection_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_hold_point: Mapped[bool] = mapped_column(Boolean, default=False)

    itp_document: Mapped[ItpDocument] = relationship(back_populates="steps")


class ConcessionWaiver(Base):
    __tablename__ = "epc_concessions_waivers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    po_number: Mapped[str] = mapped_column(String(64), index=True)
    waiver_type: Mapped[str] = mapped_column(String(32))  # ITP_HOLD_WAIVER | NCR_CONCESSION | CONCERN_WAIVER
    target_ref_id: Mapped[str] = mapped_column(String(128), index=True)
    concession_ref_no: Mapped[str] = mapped_column(String(128))
    justification: Mapped[str] = mapped_column(Text)
    approved_by_name: Mapped[str] = mapped_column(String(255))
    approved_by_role: Mapped[str] = mapped_column(String(64))
    attachment_doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
