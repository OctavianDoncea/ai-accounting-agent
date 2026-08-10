import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import health, chart_of_accounts, invoices, journal_entries, reconciliation, dashboard, reports, auth
from app.security import JWTAuthMiddleware

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('app')

app = FastAPI(title='AI Accounting Agent', description='Automated invoice ingestion, classification, and reconciliation using local LLM agents')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
app.add_middleware(JWTAuthMiddleware)

app.include_router(health.router)
app.include_router(chart_of_accounts.router)
app.include_router(invoices.router)
app.include_router(journal_entries.router)
app.include_router(reconciliation.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(auth.router)

@app.get('/', tags=['root'])
def root() -> dict:
    return {
        'name': 'AI Accounting Agent',
        'docs': '/docs',
        'health': '/health'
    }