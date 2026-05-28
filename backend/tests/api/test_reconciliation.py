class TestReonciliationUpload:
    def test_rejects_non_csv(self, client):
        r = client.post('/reconciliation/upload', files={'file': {'x.pdf', b'x', 'application/pdf'}})
        assert r.status_code == 400

    def test_rejects_empty(self, client):
        r = client.post('/reconciliation/upload', files={'file': {'empty.csv', b'', 'text/csv'}})
        assert r.status_code == 400

    def test_rejects_malformed_csv(self, client):
        r = client.post('/reconciliation/upload', files={'file': {'malformed.csv', b'Date\n2026-05-05\n', 'text/csv'}})
        assert r.status_code == 400

    def test_minimal_valid_statement_return_report(self, client):
        csv = b"Date,Description,Amount\n2026-05-05,COFFEE,-4.50\n"
        r = client.post('/reconciliation/upload', files={'file': {'stmt.csv', csv, 'text/csv'}})
        assert r.status_code == 201
        body = r.json()
        assert body['bank_transaction_count'] == 1
        assert body['unmatched_bank_count'] == 1


class TestListAndGet:
    def test_list_empty(self, client):
        assert client.get('/reconciliation/runs').json() == []

    def test_list_after_upload(self, client):
        csv = b"Date,Description,Amount\n2026-05-05,COFFEE,-4.50\n"
        client.post('/reconciliation/upload', files={'file': {'stmt.csv', csv, 'text/csv'}})
        runs = client.get('/reconciliation/runs').json()
        assert len(runs) == 1

    def test_get_nonexistent_returns_404(self, client):
        r = client.get('/reconciliation/runs/00000000-0000-0000-0000-000000000000')
        assert r.status_code == 404


class TestExport:
    def test_journal_entries_export_is_csv(self, client):
        r = client.get('/journal-entries/export')
        assert r.status_code == 200
        assert r.headers['content-type'].startswith('text/csv')
        assert b'Entry ID' in r.content

    def test_reconciliation_export_after_upload(self, client):
        csv = b"Date,Description,Amount\n2026-05-05,COFFEE,-4.50\n"
        upload = client.post('/reconciliation/upload', files={'file': {'stmt.csv', csv, 'text/csv'}}).json()
        rid = upload['id']
        r = client.get(f'/reconciliation/runs/{rid}/export')
        assert r.status_code == 200
        assert b'COFFEE' in r.content