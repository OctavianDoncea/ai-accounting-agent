import logging
import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.chart_of_accounts import ChartOfAccount
from app.services.llm_factory import create_llm_client


router = APIRouter(tags=['health'])
log = logging.getLogger(__name__)


@router.get('/health')
def health(db: Session = Depends(get_db)) -> dict:
    """Reports the status of every dependency the backend relies on."""
    # Database
    try:
        db.execute(text('SELECT 1'))
        db_ok = True
        db_error = None
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    # Chart-of-accounts count
    try:
        accounts_count = db.query(ChartOfAccount).count()
    except Exception:
        accounts_count = None

    # LLM (Ollama or Groq)
    llm_provider = settings.llm_provider
    try:
        client = create_llm_client()
        llm_ok = client.is_available()
        llm_error = None if llm_ok else 'LLM service not reachable'
    except Exception as exc:
        llm_ok = False
        llm_error = str(exc)

    overall_ok = db_ok
    return {
        'status': 'ok' if overall_ok else 'degraded',
        'database': {'ok': db_ok, 'error': db_error, 'chart_of_accounts_count': accounts_count},
        'llm': {
            'ok': llm_ok,
            "provider": llm_provider,
            'model': settings.groq_model if llm_provider == 'groq' else settings.ollama_model,
            'error': llm_error,
        },
        # Keep the old key for frontend backward compatibility
        'ollama': {
            'ok': llm_ok,
            'url': settings.ollama_url if llm_provider == 'ollama' else 'N/A (using Groq)',
            'model': settings.groq_model if llm_provider == 'groq' else settings.ollama_model,
            'error': llm_error,
        },
    }
