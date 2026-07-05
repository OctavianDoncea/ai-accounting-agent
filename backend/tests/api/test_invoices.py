from unittest.mock import patch

from tests.conftest import SAMPLE_PDF

def _patched_upload(client, filepath: str = SAMPLE_PDF, filename: str = 'invoice.pdf'):
    """Upload a file with the background processor patched out"""
    with patch('app.api.invoices.process_invoice') as mock_process:
        with open(filepath, 'rb') as f:
            r = client.post('/invoices/upload', files={'file': (filename, f.read(), 'application/pdf')})
    
    return r, mock_process

class TestUpload:
    def test_rejects_unsupported_extension(self, client):
        r = client.post('/invoices/upload', files={'file': ('note.txt', b'hello', 'text/plain')})
        assert r.status_code == 400
        assert 'Unsupported' in r.json()['detail']

    def test_rejects_empty_file(self, client):
        r = client.post('/invoices/upload', files={'file': ('empty.pdf', b'', 'application/pdf')})
        assert r.status_code == 400

    def test_accepts_psf_and_returns_pending(self, client):
        r, _ = _patched_upload(client)
        assert r.status_code == 201
        body = r.json()
        assert body['status'] == 'PENDING'
        assert 'invoice_id' in body

    def test_schedules_background_processing(self, client):
        r, mock_process = _patched_upload(client)
        assert mock_process.called


class TestListAndDetail:
    def test_list_empty(self, client):
        assert client.get('/invoices').json() == []

    def test_list_after_upload(self, client):
        _patched_upload(client)
        invoices = client.get('/invoices').json()
        assert len(invoices) == 1

    def test_get_nonexistent_returns_404(self, client):
        r = client.get('/invoices/00000000-0000-0000-0000-000000000000')
        assert r.status_code == 404

    def test_logs_for_nonexistent_returns_404(self, client):
        r = client.get('/invoices/00000000-0000-0000-0000-000000000000/logs')
        assert r.status_code == 404

    def test_journal_entry_endpoint_returns_404_when_no_je(self, client):
        r, _ = _patched_upload(client)
        iid = r.json()['invoice_id']
        assert client.get(f'/invoices/{iid}/journal-entry').status_code == 404