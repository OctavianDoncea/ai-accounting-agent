# AI Accounting Agent
 
An AI-powered accounting automation system that ingests invoices, extracts structured data, classifies them into proper double-entry journal entries, and reconciles them against bank statements — using a multi-agent architecture powered by local LLMs (Ollama).
 
## Status
 
After extraction, a classification agent maps each line item to a GL account, deterministic Python builds a balanced double-entry journal entry, and a validation agent verifies it before posting. Entries that don't balance, have low classification confidence, or required a fallback account are held as drafts for review rather than posted.
 
### Design note: LLM for judgment, code for arithmetic
 
The classification agent uses the LLM *only* to choose an account code per line item — a judgment task. The journal entry itself (debits, credits, totals, balancing) is constructed by deterministic Python, and a separate rule-based validation agent checks it. LLMs are unreliable at arithmetic but good at classification, so this split keeps the money math correct and auditable.
 
## Architecture
 
```
Upload → OCR → Extraction agent → Duplicate check
                                        │
                                        ▼
                          ┌──────────────────────────┐
                          │   Classification agent    │  ← LLM: account code per line
                          │   (judgment only)         │
                          └──────────────────────────┘
                                        │
                                        ▼
                          ┌──────────────────────────┐
                          │  Journal entry builder    │  ← Python: build double-entry
                          │  (deterministic)          │
                          └──────────────────────────┘
                                        │
                                        ▼
                          ┌──────────────────────────┐
                          │   Validation agent        │  ← Python: debits == credits,
                          │   (deterministic rules)   │     accounts valid, no negatives
                          └──────────────────────────┘
                                        │
                              ┌─────────┴─────────┐
                              ▼                   ▼
                         POSTED              NEEDS_REVIEW
                    (valid + confident)   (imbalance / low conf / fallback)
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
│       │   └── validation_agent.py     # deterministic double-entry validation
│       ├── services/
│       │   ├── ocr.py                  # PDF/image → text
│       │   ├── ollama_client.py        # local LLM client
│       │   ├── duplicate_detection.py
│       │   ├── journal_entry_builder.py# deterministic double-entry construction
│       │   ├── agent_logger.py         # audit-trail helper
│       │   └── invoice_processor.py    # pipeline orchestrator
│       └── api/                        # health, chart_of_accounts, invoices, journal_entries
└── frontend/
    ├── Dockerfile
    ├── requirements.txt
    ├── app.py                          # (or main.py) home / status page
    └── pages/
        ├── 1_Upload_Invoice.py
        ├── 2_Invoices.py               # detail + journal entry + audit trail
        └── 3_Journal.py                # all journal entries
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