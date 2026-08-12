class TestHealth:
    def test_returns_db_status(self, client):
        r = client.get('/health')
        assert r.status_code == 200
        body = r.json()
        assert 'database' in body
        assert 'ollama' in body
        assert body['database']['ok'] is True

    def test_ready_reports_database(self, client):
        r = client.get('/ready')
        assert r.status_code == 200
        body = r.json()
        assert body['ready'] is True
        assert 'auth_enabled' in body

    def test_chart_of_accounts_count_visible(self, client):
        body = client.get('/health').json()
        assert body['database']['chart_of_accounts_count'] > 0


class TestRoot:
    def test_root_returns_meta(self, client):
        r = client.get('/')
        assert r.status_code == 200
        body = r.json()
        assert body['name'] == 'AI Accounting Agent'
        

class TestChartOfAccounts:
    def test_list_returns_seeded_accounts(self, client):
        r = client.get('/chart-of-accounts')
        assert r.status_code == 200
        accounts = r.json()
        codes = {a['account_code'] for a in accounts}
        assert '1000' in codes
        assert '2000' in codes
        assert '6210' in codes
        assert '6920' in codes
        assert '7900' in codes

    def test_filter_by_account_type(self, client):
        r = client.get('/chart-of-accounts?account_type=EXPENSE')
        accounts = r.json()
        assert len(accounts) > 0
        assert all(a['account_type'] == 'EXPENSE' for a in accounts)


class TestDashboard:
    def test_summary_with_empty_db(self, client):
        body = client.get('/dashboard/summary').json()
        assert body['total_invoices'] == 0
        assert body['journal_entries_posted'] == 0
        assert body['recent_invoices'] == []


class TestReports:
    def test_trial_balance_empty_db(self, client):
        body = client.get('/reports/trial-balance').json()
        assert body['rows'] == []
        assert body['is_balanced'] is True

    def test_expense_breakdown_empty_db(self, client):
        assert client.get('/reports/expense-breakdown').json() == []