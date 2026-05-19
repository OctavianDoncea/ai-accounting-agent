import enum
import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime, Enum, Text, func, ForeignKey, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base

class InvoiceStatus(str, enum.Enum):
    PENDING = 'PENDING'
    EXTRACTED = 'EXTRACTED'
    CLASSIFIED = 'CLASSIFIED'
    POSTED = 'POSTED'
    DUPLICATE = 'DUPLICATE'
    NEEDS_REVIEW = 'NEEDS_REVIEW'
    FAILED = 'FAILED'


class Invoice(Base):
    __tablename__ = 'invoices'

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    upload_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus, name='invoice_status'), default=InvoiceStatus.PENDING, nullable=False, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=False)
    vendor_name: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    invoice_number: Mapped[str | None] = mapped_column(Date, nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    tax: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default='USD')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    line_items: Mapped[list['InvoiceLineItems']] = relationship(back_populates='invoice', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f'<Invoice {self.id} - {self.vendor_name or "unknown"} - {self.status}>'


class InvoiceLineItems(Base):
    __tablename__ = 'invoice_line_items'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    invoice_id: Mapped[Decimal] = mapped_column(UUID(as_uuid=True), ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal('1'), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(15, ), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice: Mapped['Invoice'] = relationship(back_populates='line_items')

    def __repr__(self) -> str:
        return f'<InvoiceLineItem {self.description[:30]} - {self.amount}>'