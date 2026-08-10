import logging
import time
import uuid
from contextlib import contextmanager
from sqlalchemy.orm import Session
from app.models.agent_log import AgentLog, AgentLogStatus

log = logging.getLogger(__name__)

def write_log(db:Session,
    *,
    invoice_id: uuid.UUID | None = None,
    agent_name: str,
    step_name: str,
    status: AgentLogStatus,
    input_data: dict | None = None,
    output_data: dict | None = None,
    reasoning: str | None = None,
    confidence_score: float | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    user_id: uuid.UUID | None = None,
) -> AgentLog:
    entry = AgentLog(
        invoice_id=invoice_id,
        agent_name=agent_name,
        step_name=step_name,
        status=status,
        input_data=_json_safe(input_data),
        output_data=_json_safe(output_data),
        reasoning=reasoning or error_message or 'Step completed.',
        confidence_score=confidence_score,
        error_message=error_message,
        duration_ms=duration_ms,
        user_id=user_id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry

@contextmanager
def time_step(db: Session, *, invoice_id: uuid.UUID | None, agent_name: str, step_name: str, input_data: dict | None = None, user_id: uuid.UUID | None = None):
    """Context manager that times a step and writes a log entry on exit"""
    started = time.monotonic()
    ctx: dict = {'output_data': None, 'reasoning': None, 'confidence_score': None}
    try:
        yield ctx
    except Exception as e:
        db.rollback()
        duration = int((time.monotonic() - started) * 1000)
        write_log(
            db,
            invoice_id=invoice_id,
            agent_name=agent_name,
            step_name=step_name,
            status=AgentLogStatus.FAILED,
            input_data=input_data,
            reasoning=f'Step failed: {e}',
            error_message=str(e),
            duration_ms=duration,
            user_id=user_id,
        )
        raise
    else:
        duration = int((time.monotonic() - started) * 1000)
        try:
            write_log(
                db,
                invoice_id=invoice_id,
                agent_name=agent_name,
                step_name=step_name,
                status=ctx.get('status', AgentLogStatus.SUCCESS),
                input_data=input_data,
                output_data=ctx.get('output_data'),
                reasoning=ctx.get('reasoning') or 'Step completed successfully.',
                confidence_score=ctx.get('confidence_score'),
                duration_ms=duration,
                user_id=user_id,
            )
        except Exception:
            db.rollback()
            raise

def _json_safe(data: dict | None) -> dict | None:
    if data is None:
        return None
    import json
    from datetime import datetime, date
    from decimal import Decimal

    def default(obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        
        return str(obj)

    return json.loads(json.dumps(data, default=default))