from pydantic import BaseModel, Field

class LineOverride(BaseModel):
    line_id: int
    account_code: str


class ReviewSubmission(BaseModel):
    overrides: list[LineOverride] = Field(default_factory=list)
    tax_account_code: str | None = None


class ClassifiableAccountOut(BaseModel):
    account_code: str
    account_name: str
    account_type: str


class ReviewLineItemOut(BaseModel):
    line_id: int
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float
    current_account_code: str | None = None


class ReviewDetailOut(BaseModel):
    invoice_id: str
    filename: str
    vendor_name: str | None
    invoice_number: str | None
    total: float | None
    tax: float | None
    currency: str
    status: str
    line_items: list[ReviewLineItemOut]
    current_tax_account_code: str | None = None
    classifiable_accounts: list[ClassifiableAccountOut]
    validation_errors: list[str] = Field(default_factory=list)


class ReviewSubmitResponse(BaseModel):
    invoice_id: str
    invoice_status: str
    journal_entry_status: str
    is_balanced: bool
    validation_errors: list[str] = Field(default_factory=list)