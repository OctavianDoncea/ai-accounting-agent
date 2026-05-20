import logging
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.chart_of_accounts import ChartOfAccount

router = APIRouter(tags=['health'])
log = logging.getLogger(__name__)

@router.get('/health')
def health(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text('SELECT 1'))
        db_ok = True
        db_error = None
    except Exception as e:
        db_ok = False
        db_error = str(e)

    try:
        accounts_count = db.query(ChartOfAccount).count()
    except Exception:
        accounts_count = None

    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f'{settings.ollama_url}/api/tags')
        ollama_ok = resp.status_code == 200
        ollama_error = None if ollama_ok else f'HTTP {resp.status_code}'
    except Exception as e:
        ollama_ok = False
        ollama_error = str(e)

    overall_ok = db_ok
    return {
        'status': 'ok' if overall_ok else 'degraded',
        'database': {'ok': db_ok, 'error': db_error, 'chart_of_accounts_count': accounts_count},
        'ollama': {'ok': ollama_ok, 'url': settings.ollama_url, 'model': settings.ollama_model, 'error': ollama_error}
    }