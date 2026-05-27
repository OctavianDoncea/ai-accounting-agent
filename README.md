# AI Accounting Agent
 
An AI-powered accounting automation system that ingests invoices, extracts structured data, classifies them into proper double-entry journal entries, and reconciles them against bank statements — using a multi-agent architecture powered by local LLMs (Ollama).
 
## Status
 
**Phase 4: Bank Reconciliation Agent** — complete
 
Upload a bank-statement CSV and the reconciliation agent matches each payment against the posted journal entries, surfacing three things: payments matched to recorded bills, payments with no matching invoice (possible missing invoices), and posted bills with no payment (possibly unpaid). Matching is deterministic — amount + date window + fuzzy vendor-name matching — so it stays fast and reliable across statements with many rows.
 
## Architecture
 
```
Bank statement CSV
       │
       ▼
┌────────────────────┐   transactions   ┌──────────────────────────┐
│ Bank statement     │ ───────────────▶ │  Reconciliation agent     │
│ parser             │                  │  (deterministic matching) │
│ (signed / debit-   │                  │  amount + date + fuzzy    │
│  credit / typed)   │                  │  vendor-name similarity   │
└────────────────────┘                  └──────────────────────────┘
                                                     │
                          ┌──────────────────────────┼──────────────────────────┐
                          ▼                           ▼                          ▼
                     MATCHED                    UNMATCHED payment          UNMATCHED journal entry
                  (bill was paid)            (possible missing invoice)   (posted bill, possibly unpaid)
```
 
## Prerequisites
 
- Docker + Docker Compose
- Ollama installed on host machine (https://ollama.com)
- ~6 GB free disk space for the LLM model
## Setup
 
### 1. Install Ollama and pull a model
 
```bash
# Install Ollama from https://ollama.com (one-line install on Linux/Mac)
# Then pull a model:
ollama pull llama3.1:8b
 
# Verify it's running:
curl http://localhost:11434/api/tags
```
 
### 2. Clone the repo and configure environment
 
```bash
git clone https://github.com/YOUR_USERNAME/ai-accounting-agent.git
cd ai-accounting-agent
cp .env.example .env
```
 
### 3. Start the stack
 
```bash
docker compose up --build
```
 
This will:
- Start PostgreSQL
- Build and start the FastAPI backend
- Build and start the Streamlit frontend
- The backend automatically runs migrations and seeds the chart of accounts on startup
### 4. Verify everything works
 
- Backend health check: http://localhost:8000/health
- API docs (Swagger): http://localhost:8000/docs
- Frontend: http://localhost:8501
The frontend page should show a green "Backend OK" status.
 
## API endpoints
 
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | DB + Ollama status |
| GET | `/chart-of-accounts` | List GL accounts |
| POST | `/invoices/upload` | Upload an invoice (PDF/image); processing starts in background |
| GET | `/invoices` | List invoices (optional `?status=` filter) |
| GET | `/invoices/{id}` | Invoice detail with line items |
| GET | `/invoices/{id}/logs` | Full agent audit trail for an invoice |
| POST | `/invoices/{id}/reprocess` | Re-run the full pipeline on an invoice |
| GET | `/invoices/{id}/journal-entry` | The journal entry generated for an invoice |
| POST | `/invoices/{id}/reclassify` | Re-run only classification + validation |
| GET | `/journal-entries` | List all journal entries |
| GET | `/journal-entries/{id}` | Journal entry detail with debit/credit lines |
| POST | `/reconciliation/upload` | Upload a bank CSV; returns the reconciliation report |
| GET | `/reconciliation/runs` | List past reconciliation runs |
| GET | `/reconciliation/runs/{id}` | Full report for a reconciliation run |
 
## Trying it out
 
1. Make sure Ollama is running with the model pulled: `ollama pull llama3.1:8b`
2. `docker compose up --build`
3. Generate sample invoices (one-time): `python samples/generate_samples.py`
4. Open the frontend at http://localhost:8501 → **Upload Invoice** → drop in `samples/invoice_cloudhost.pdf`
5. Watch it process, then view the extracted fields and agent audit trail on the **Invoices** page
6. Upload the same file again to see duplicate detection in action
Or via the API:
 
```bash
curl -F "file=@samples/invoice_cloudhost.pdf" http://localhost:8000/invoices/upload
# → {"invoice_id": "...", "status": "PENDING", ...}
curl http://localhost:8000/invoices/<invoice_id>
```
 
## Database Schema
 
| Table | Purpose |
|---|---|
| `chart_of_accounts` | GL account list (Assets, Liabilities, Revenue, etc.) |
| `invoices` | Uploaded invoice metadata + status |
| `invoice_line_items` | Extracted line items per invoice |
| `journal_entries` | Double-entry bookkeeping records |
| `journal_entry_lines` | Individual debit/credit lines |
| `agent_logs` | Audit trail of every agent decision |
 
## Project Structure
 
```
ai-accounting-agent/
├── docker-compose.yml
├── .env.example
├── samples/                        # sample invoice PDFs + generator
│   ├── generate_samples.py
│   └── invoice_*.pdf
├── backend/
│   ├── Dockerfile                  # now includes tesseract-ocr + poppler
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── migrations/
│   └── app/
│       ├── main.py                 # FastAPI entrypoint
│       ├── config.py               # Settings (env vars)
│       ├── database.py             # SQLAlchemy session
│       ├── models/                 # ORM models
│       ├── schemas/                # Pydantic request/response models
│       ├── seed/                   # Chart of accounts seed data
│       ├── agents/
│       │   ├── extraction_agent.py     # LLM: extract fields from text
│       │   ├── classification_agent.py # LLM: map line items to GL accounts
│       │   ├── validation_agent.py     # deterministic double-entry validation
│       │   └── reconciliation_agent.py # deterministic bank matching
│       ├── services/
│       │   ├── ocr.py                  # PDF/image → text
│       │   ├── ollama_client.py        # local LLM client
│       │   ├── duplicate_detection.py
│       │   ├── journal_entry_builder.py# deterministic double-entry construction
│       │   ├── bank_statement_parser.py# CSV → normalized transactions
│       │   ├── reconciliation_processor.py
│       │   ├── agent_logger.py         # audit-trail helper
│       │   └── invoice_processor.py    # pipeline orchestrator
│       └── api/                        # health, chart_of_accounts, invoices,
│                                       #   journal_entries, reconciliation
└── frontend/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py                          # (or main.py) home / status page
    └── pages/
        ├── 1_Upload_Invoice.py
        ├── 2_Invoices.py               # detail + journal entry + audit trail
        ├── 3_Journal.py                # all journal entries
        └── 4_Reconciliation.py         # bank statement matching
```
 
## Useful commands
 
```bash
# Tail logs
docker compose logs -f backend
 
# Open a Postgres shell
docker compose exec postgres psql -U accounting -d accounting_db
 
# Run migrations manually
docker compose exec backend alembic upgrade head
 
# Create a new migration after changing models
docker compose exec backend alembic revision --autogenerate -m "your message"
 
# Stop everything
docker compose down
 
# Reset everything (including the database)
docker compose down -v
```