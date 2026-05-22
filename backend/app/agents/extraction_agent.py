import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from dateutil import parser as date_parser
from app.schemas.invoice import ExtractedInvoice, ExtractedLineItem
from app.services.ollama_client import OllamaClient, OllamaError

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert accounting data-extraction agent. \
You are given the raw text of a single invoice (it may be messy OCR output). \
Extract the structured fields and return ONLY a JSON object — no prose, no markdown.
 
The JSON object must have exactly these keys:
{
  "vendor_name": string or null,        // the company that ISSUED the invoice (the seller), not the recipient
  "invoice_number": string or null,
  "invoice_date": string or null,       // ISO format YYYY-MM-DD if possible
  "due_date": string or null,           // ISO format YYYY-MM-DD if possible
  "currency": string,                   // 3-letter ISO code, e.g. "USD", "EUR". Default "USD" if unclear
  "subtotal": number or null,           // amount before tax
  "tax": number or null,
  "total": number or null,              // grand total including tax
  "line_items": [
    {
      "description": string,
      "quantity": number,
      "unit_price": number,
      "amount": number                  // line total = quantity * unit_price
    }
  ],
  "confidence": number,                 // 0.0 to 1.0 — your confidence in the overall extraction
  "reasoning": string                   // one or two sentences explaining your extraction or any uncertainty
}
 
Rules:
- vendor_name is the SELLER (who is owed money), never the "Bill To" recipient.
- Numbers must be plain numbers: no currency symbols, no thousands separators.
- If a value is genuinely absent, use null (do not invent values).
- If totals don't add up or text is ambiguous, lower your confidence and explain in reasoning.
"""

USER_PROMPT_TEMPLATE = """Extract the invoice fields from the following text:

--- BEGIN INVOICE TEXT ---
{invoice_text}
--- END INVOICE TEXT ---

Return only the JSON object."""

class ExtractionAgent:
    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()

    def extract(self, invoice_text: str) -> ExtractedInvoice:
        """Run extraction with one retry on validation failure"""
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                raw = self.client.chat_json(SYSTEM_PROMPT, USER_PROMPT_TEMPLATE.format(invoice_text=invoice_text[:8000]))
                return self._normalize(raw)
            except (OllamaError, ValueError) as e:
                last_error = e
                log.warning(f'Extraction attempt {attempt} failed: {e}')
        raise OllamaError(f'Extraction failed after retries: {last_error}')

    def _normalize(self, raw: dict) -> ExtractedInvoice:
        line_items = []
        for item in raw.get('line_items') or []:
            if not isinstance(item, dict):
                continue
            desc = str(item.get('description') or '').strip()
            if not desc:
                continue
            line_items.append(
                ExtractedLineItem(
                    description=desc[:500],
                    quantity=_to_decimal(item.get('quantity')) or Decimal('1'),
                    unit_price=_to_decimal(item.get('unit_price')) or Decimal('0'),
                    amount=_to_decimal(item.get('amount')) or Decimal('0'),
                )
            )

        confidence = raw.get('confidence')
        try:
            confidence = float(confidence)
            confidence = min(max(confidence, 0.0), 1.0)
        except (ValueError, TypeError):
            confidence = 0.5
        

        return ExtractedInvoice(
            vendor_name=_clean_str(raw.get('vendor_name')),
            invoice_number=_clean_str(raw.get('invoice_number')),
            invoice_date=_to_date(raw.get('invoice_date')),
            due_date=_to_date(raw.get('due_date')),
            currency=(_clean_str(raw.get('currency')) or 'USD')[:3].upper(),
            subtotal=_to_decimal(raw.get('subtotal')),
            tax=_to_decimal(raw.get('tax')),
            total=_to_decimal(raw.get('total')),
            line_items=line_items,
            confidence=confidence,
            reasoning=_clean_str(raw.get('reasoning')),
        )

def _clean_str(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    
    return s or None

def _to_decimal(value) -> Decimal | None:
    if value is None or value == '':
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))

    cleaned = str(value).strip()
    for ch in ['$', '€', '£', '¥', '', ',']:
        cleaned = cleaned.replace(ch, '')
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None

def _to_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date_parser.parse(str(value), fuzzy=True).date()
    except (ValueError, TypeError):
        return None