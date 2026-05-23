import uuid
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from app.models.journal_entry import JournalEntryStatus

# Classification agent output (LLM judgement only, no arithmetic)
class LineClassification(BaseModel):
    line_index: int
    account_code: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str | None = None


class ClassificationResult(BaseModel):
    classifications: list[LineClassification] = Field(default_factory=list)
    tax_account_code: str | None = None
    overall_reasoning: str | None = None

    @property
    def min_confidence(self) -> float:
        if not self.classifications:
            return 0.0
        return min(cls.confidence for cls in self.classifications)

# Validation result (deterministic)
class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

# API response models
class JournalEntryLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    account_code: str | None = None
    account_name: str | None = None
    debit_amount: Decimal
    credit_amount: Decimal
    description: str | None
    confidence_score: float | None


class JournalEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID | None
    entry_date: date
    description: str
    status: JournalEntryStatus
    total_debit: Decimal
    total_credit: Decimal
    created_at: datetime
    lines: list[JournalEntryLineOut] = Field(default_factory=list)

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_debit - self.total_credit) <= Decimal('0.01')