import logging
from app.models.chart_of_accounts import ChartOfAccount
from app.schemas.journal_entry import ClassificationResult, LineClassification
from app.services.ollama_client import OllamaClient, OllamaError

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert accounting classification agent. \
You are given a vendor invoice (its line items) and a chart of accounts. \
For each line item, choose the single most appropriate general-ledger account to DEBIT \
(this is a purchase/bill, so each line item is an expense or an asset). \
Return ONLY a JSON object — no prose, no markdown.
 
The JSON object must have exactly these keys:
{
  "classifications": [
    {
      "line_index": integer,      // the index of the line item, as given to you
      "account_code": string,     // the chosen account code from the chart of accounts
      "confidence": number,       // 0.0 to 1.0
      "reasoning": string         // brief justification for the chosen account
    }
  ],
  "tax_account_code": string or null,  // account code to use for any sales tax (if applicable)
  "overall_reasoning": string
}
 
Rules:
- Choose account_code values ONLY from the provided chart of accounts.
- Match the business purpose of each item to the closest account (e.g. cloud servers -> Cloud Hosting; legal work -> Professional Fees; chairs/desks -> Office Equipment or Office Supplies).
- If nothing fits well, choose the closest expense account and lower your confidence.
- For tax, prefer an account whose name relates to sales tax; otherwise use a general expense account.
- Provide one classification object per line item, using the exact line_index given.
"""

def _format_accounts(accounts: list[ChartOfAccount]) -> str:
    lines = []
    for a in accounts:
        lines.append(f'  {a.account_code}  {a.account_name}  ({a.account_type.value})')
    return '\n'.join(lines)

def _format_line_items(line_items) -> str:
    lines = []
    for i, li in enumerate(line_items):
        lines.append(f'  [{i}] {li.description} (amount: {li.amount})')
    return '\n'.join(lines) if lines else ' (no line items extracted)'

class ClassificationAgent:
    def __init__(self, client: OllamaClient | None = None):
        self.client = client or OllamaClient()

    def classify(self, invoice, accounts: list[ChartOfAccount]) -> ClassificationResult:
        """Classify an invoice's line items against the chart of accounts"""
        user_prompt = (
            f"Vendor: {invoice.vendor_name or 'unknown'}\n"
            f'Invoice total: {invoice.total} {invoice.currency}\n'
            f"Tax amount: {invoice.tax if invoice.tax is not None else 'none'}\n\n"
            f'Line items:\n{_format_line_items(invoice.line_items)}\n\n'
            f'Available chart of accounts (code name type):\n{_format_accounts(accounts)}\n\n'
            f'Return only the JSON object.'
        )

        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                raw = self.client.chat_json(SYSTEM_PROMPT, user_prompt)
                return self._normalize(raw)
            except (OllamaError, ValueError) as e:
                last_error = e
                log.warning(f'Classification attempt {attempt} failed: {e}')
        raise OllamaError(f'Classification failed after retries: {last_error}')

    def _normalize(self, raw: dict, invoice) -> ClassificationResult:
        classifications = []
        for c in raw.get('classifications') or []:
            if not isinstance(c, dict):
                continue
            try:
                idx = int(c.get('line_index'))
            except (TypeError, ValueError):
                continue
            code = str(c.get('account_code') or '').strip()
            if not code:
                continue
            conf = c.get('confidence')
            try:
                conf = min(max(float(conf), 0.0), 1.0)
            except (TypeError, ValueError):
                conf = 0.5
            classifications.append(LineClassification(line_index=idx, account_code=code, confidence=conf, reasoning=str(c.get('reasoning') or '').strip() or None))

        tax_code = raw.get('tax_account_code')
        tax_code = str(tax_code).strip() if tax_code else None

        return ClassificationResult(
            classifications=classifications,
            tax_account_code=tax_code,
            overall_reasoning=str(raw.get('overall_reasoning') or '').strip() or None,
        )