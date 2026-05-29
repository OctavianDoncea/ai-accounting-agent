# AI Accounting Agent
 
An AI-powered accounting automation system that ingests invoices, extracts structured data, classifies them into proper double-entry journal entries, and reconciles them against bank statements — using a multi-agent architecture powered by local LLMs (Ollama).
 
## Problem & motivation
 
Small business owners and finance teams spend a disproportionate amount of their week on rote bookkeeping: keying invoice data into accounting software, mapping each line to the right GL account, and reconciling bank statements line-by-line. The work is mostly judgment-light pattern recognition that LLMs and structured pipelines are well-suited to automate end-to-end.
 
This project is an end-to-end demonstration: drop a PDF in, and the system OCRs it, extracts the structured fields, classifies each line to a GL account, builds a balanced double-entry journal entry, validates it, and posts it — with a full audit trail of every decision. Upload a bank CSV and it matches payments back to those entries.
 
### Design philosophy: LLM for judgment, code for arithmetic
 
A core design call worth highlighting: **the LLM is used only for judgment tasks** (extracting fields from messy OCR text, picking a GL account for each line item). All arithmetic — building the double-entry, computing totals, balancing debits against credits, validating the entry, matching bank transactions — is deterministic Python. LLMs are unreliable at arithmetic, and the rules of double-entry bookkeeping are inviolable. Keeping the money math out of the model means the books stay correct, fast, and auditable.

### UI surfaces
 
| Page | What it does |
|---|---|
| **Home / Dashboard** | KPI cards, system status, recent invoices and reconciliation runs, quick actions |
| **Upload Invoice** | Drop a PDF or image; polls for status with a stepwise progress bar (OCR → extract → dedupe → classify → build → validate) and shows the final extracted fields |
| **Invoices** | Filterable list with status badges and per-status count strip; full detail with line items, journal entry, and the agent audit trail; reprocess / reclassify buttons |
| **Journal** | All journal entries with status filter, balanced/unbalanced markers, one-click CSV export |
| **Reconciliation** | Upload a new statement or open any past run; three result tables (matched / unmatched payments / unpaid bills) plus a CSV export |
| **Chart of Accounts** | Filterable GL account list with per-type counts |
| **Reports** | Trial balance (debits, credits, balance per account) and a spending-by-category bar chart |
 
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
| GET | `/journal-entries/export` | Download all journal entries as CSV |
| GET | `/reconciliation/runs/{id}/export` | Download a reconciliation report as CSV |
| GET | `/dashboard/summary` | KPIs + recent activity for the home page |
| GET | `/reports/trial-balance` | Trial balance from posted entries |
| GET | `/reports/expense-breakdown` | Total spend per expense account |
 
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
│                                       #   journal_entries, reconciliation,
│                                       #   dashboard, reports
└── frontend/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py                          # (or main.py) home dashboard
    ├── ui_helpers.py                   # shared badges + formatting
    └── pages/
        ├── 1_Upload_Invoice.py
        ├── 2_Invoices.py               # detail + journal entry + audit trail
        ├── 3_Journal.py                # all entries with status filter + CSV
        ├── 4_Reconciliation.py         # upload + past runs + CSV
        ├── 5_Chart_of_Accounts.py
        └── 6_Reports.py                # trial balance + spending chart
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
 
## Testing
 
The backend has 115 tests covering the agents, pipelines, schema, and HTTP layer.
 
```bash
# Inside the backend container (or with backend deps installed locally):
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.seed.run_seed
pytest tests/                                 # all 115 tests in ~3 seconds
pytest tests/ --cov=app --cov-report=term     # with coverage
pytest tests/unit/                            # just the no-DB unit tests
pytest tests/ -k duplicate -v                 # name-filter tests
```
 
| Layer | Tests | Covers |
|---|---|---|
| `tests/unit/` | extraction normalization, reconciliation matching, bank statement parser, OCR | Pure functions; no DB or LLM |
| `tests/integration/` | journal entry builder, validation agent, duplicate detection, invoice processor (full pipeline), reconciliation processor | Real Postgres; LLM mocked |
| `tests/api/` | health, invoices, reconciliation, dashboard, reports, CSV exports | FastAPI TestClient |
 
CI runs on every push and pull request via `.github/workflows/ci.yml`: spins up a Postgres service, installs Tesseract and Poppler, runs migrations, seeds the chart of accounts, and executes the full test suite.
 
## Deployment
 
The project is designed to run locally with Docker Compose. A live public deployment is intentionally not included by default because:
 
- **Ollama is local.** It runs on the host machine, not in containers. To deploy to a cloud free tier (Render, Fly.io, Railway), you'd need to swap Ollama for a hosted API such as Groq, Anthropic, or OpenAI.
- **The simplest path to a public demo** is to add a `GroqClient` parallel to `OllamaClient` (Groq has a free tier and an OpenAI-compatible chat API) and select between them via an `LLM_PROVIDER` env var. The agent code is already structured to make this a single-file change.
- **The current Docker Compose stack** is production-ready in shape: healthchecks on Postgres, the backend runs migrations on startup, the frontend is served standalone. Pointing it at managed Postgres and deploying behind a reverse proxy is straightforward.
For evaluators: clone the repo, install Ollama and `llama3.1:8b`, run `docker compose up --build`, and the system is live at http://localhost:8501 in about two minutes.
 
## Limitations & future work
 
Things deliberately not solved in this scope, in rough priority order if it were a real product:
 
- **Cash-vs-credit posting.** Every invoice currently credits Accounts Payable (treated as a bill received). Real systems infer whether the invoice was paid on the spot (credit card or cash) versus owed (AP) — either from the invoice text or by the bank reconciliation feeding back. Adding this is straightforward: another LLM-judgment step on the invoice plus a feedback loop from reconciliation.
- **Sales tax treatment.** Tax is treated as a non-recoverable expense (correct for most US sales tax on business purchases, wrong for VAT-recoverable jurisdictions). A real product would need jurisdiction-aware tax handling.
- **Reconciliation uses fuzzy strings.** When amount + date give multiple candidates and names are genuinely ambiguous, an LLM disambiguation step (called only on the tied cases — a few per statement, not hundreds) would help.
- **No multi-tenancy or auth.** Single-user assumed throughout.
- **Vision-only invoices.** Currently uses Tesseract OCR + a text LLM. Modern vision-language models (e.g. `llama3.2-vision`) could read invoice PDFs directly and likely do better on complex layouts.
- **Confidence thresholds are constants.** Production-grade: tune them per vendor or per account type based on historical accuracy.