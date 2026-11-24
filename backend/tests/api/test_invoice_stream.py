"""Tests for the SSE progress-stream endpoint."""

import uuid
import pytest
from datetime import date
from decimal import Decimal
from app.config import settings
from app.models.agent_log import AgentLog, AgentLogStatus
from app.models.invoice import Invoice, InvoiceStatus

def _terminal_invoice(db, user_id=None) -> uuid.UUID:
    inv = Invoice(
        id=uuid.uuid4(), filename='x.pdf', file_path='/tmp/x.pdf',
        status=InvoiceStatus.POSTED, vendor_name='V', total=Decimal('100'),
        currency='USD', invoice_date=date(2026, 4, 15), user_id=user_id,
    )
    db.add(inv)
    db.flush()
    db.add(AgentLog(
        invoice_id=inv.id, user_id=user_id, agent_name='pipeline',
        step_name='final_status', status=AgentLogStatus.SUCCESS, reasoning='done',
    ))
    db.commit()
    return inv.id

class TestStreamNoAuth:
    def test_terminal_invoice_emits_progress_and_done(self, db, client):
        iid = _terminal_invoice(db)
        with client.stream('GET', f'/invoices/{iid}/stream') as r:
            assert r.status_code == 200
            body = ''.join(r.iter_text())
        assert 'event: progress' in body
        assert 'event: done' in body
        assert 'POSTED' in body

    def test_unknown_invoice_404(self, client):
        r = client.get(f'/invoices/{uuid.uuid4()}/stream')
        assert r.status_code == 404


class TestStreamAuth:
    @pytest.fixture
    def auth_on(self):
        settings.jwt_secret = 'stream-test-secret-key-32bytes!!'
        yield
        settings.jwt_secret = ''

    def test_no_token_401(self, db, client, auth_on):
        r = client.get(f'/invoices/{uuid.uuid4()}/stream')
        assert r.status_code == 401

    def test_token_as_query_param_accepted_by_middleware(self, db, client, auth_on):
        signup = client.post('/auth/signup', json={'email': 's@example.com', 'password': 'password123'})
        token = signup.json()['access_token']

        r_accepted = client.get(f'/invoices/{uuid.uuid4()}/stream?access_token={token}')
        assert r_accepted.status_code == 404

        r_rejected = client.get(f'/invoices/{uuid.uuid4()}/stream')
        assert r_rejected.status_code == 401

    def test_query_param_token_only_accepted_on_stream_paths(self, db, client, auth_on):
        signup = client.post('/auth/signup', json={'email': 'q@example.com', 'password': 'password123'})
        token = signup.json()['access_token']
        r = client.get(f'/invoices?access_token={token}')
        assert r.status_code == 401

    def test_other_users_invoice_404(self, db, client, auth_on):
        owner = client.post('/auth/signup', json={'email': 'owner@example.com', 'password': 'password123'})
        owner_token = owner.json()['access_token']
        import jwt as pyjwt
        owner_id = uuid.UUID(pyjwt.decode(owner_token, settings.jwt_secret, algorithms=['HS256'])['sub'])
        iid = _terminal_invoice(db, user_id=owner_id)

        other = client.post('/auth/signup', json={'email': 'other@example.com', 'password': 'password123'})
        other_token = other.json()['access_token']
        r = client.get(f'/invoices/{iid}/stream?access_token={other_token}')
        assert r.status_code == 404