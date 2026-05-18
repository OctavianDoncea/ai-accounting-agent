# AI Accounting Agent

An AI-powered accounting automation system that ingests invoices, extracts structured data, classifies them into proper double-entry journal entries, and reconciles them against bank statements — using a multi-agent architecture powered by local LLMs (Ollama).

## Prerequisites

- Docker + Docker Compose
- Ollama installed on host machine 
- ~6 GB free disk space for the LLM model

## Setup

### 1. Install Ollama and pull a model

```bash
# Install Ollama from https://ollama.com (one-line install on Linux/Mac)
# Then pull a model:
ollama pull llama3.1:8b

# Verify it's running
curl http://localhost:11434/api/tags
```

### 2. Clone the repo and configure environment

```bash
git clone https://github.com/OctavianDoncea/ai-accounting-agent.git
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

### 4. Verify that everything works

- Backend health check: http://localhost:8000/health
- API docs (Swagger): http://localhsot:8000/docs
- Frontend: http://localhost:8501

The frontend page should show a green "Backend OK" status.

## Database Schema
 
| Table | Purpose |
|---|---|
| `chart_of_accounts` | GL account list (Assets, Liabilities, Revenue, etc.) |
| `invoices` | Uploaded invoice metadata + status |
| `invoice_line_items` | Extracted line items per invoice |
| `journal_entries` | Double-entry bookkeeping records |
| `journal_entry_lines` | Individual debit/credit lines |
| `agent_logs` | Audit trail of every agent decision |

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