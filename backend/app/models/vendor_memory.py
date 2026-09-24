import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class VendorAccountMemory(Base):
    __tablename__ = 'vendor_account_memory'
    __table_args__ = UniqueConstraint('user_id', 'vendor_key', 'account_code', name='uq_vendor_memory_user_vendor_account')

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True)
    vendor_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    vendor_display: Mapped[str] = mapped_column(String(320), nullable=False)
    account_code: Mapped[str] = mapped_column(String(20), nullable=False)
    times_seen: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_At: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_At: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


def normalize_vendor(name: str | None) -> str:
    return (name or '').strip().lower()