import uuid
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from app.models.invoice import InvoiceStatus

# Extraction agent output (what the LLM returns, after validation)
class ExtractedLineItem(BaseModel):
    description: str
    quantity: Decimal = Decimal('1')
    unit_price: Decimal = Decimal('0')
    amount: Decimal = Decimal('0')


class ExtractedInvoice(BaseModel):
    vendor_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str = 'USD'
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str | None = None


# API response models
class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: InvoiceStatus
    upload_date: datetime
    error_message: str | None
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str
    line_items: list[LineItemOut] = Field(default_factory=list)


class InvoiceSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    status: InvoiceStatus
    upload_date: datetime
    vendor_name: str | None
    invoice_date: date | None
    total: Decimal | None
    currency: str


class AgentLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    agent_name: str
    step_name: str
    reasoning: str | None
    confidence_score: float | None
    status: str
    error_message: str | None
    duration_ms: int | None
    created_at: datetime


class UploadResponse(BaseModel):
    invoice_id: uuid.UUID
    status: InvoiceStatus
    message: str