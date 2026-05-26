import os
import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Invoices', layout='wide')
st.title('Invoices')

STATUS_BADGE = {
    'PENDING': 'Pending',
    'EXTRACTED': 'Extracted',
    'CLASSIFIED': 'Classified',
    'POSTED': 'Posted',
    'DUPLICATE': 'Duplicate',
    'NEEDS_REVIEW': 'Needs review',
    'FAILED': 'Failed',
}

@st.cache_data(ttl=3)
def fetch_invoices():
    return requests.get(f'{BACKEND_URL}/invoices', timeout=10).json()

def fetch_details(invoice_id):
    return requests.get(f'{BACKEND_URL}/invoices/{invoice_id}', timeout=10).json()

def fetch_logs(invoice_id):
    return requests.get(f'{BACKEND_URL}/invoices/{invoice_id}/logs', timeout=10).json()

def fetch_journal_entry(invoice_id):
    r = requests.get(f'{BACKEND_URL}/invoices/{invoice_id}/journal_entry', timeout=10)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()

col_refresh, _ = st.columns([1, 5])
if col_refresh.button('Refresh'):
    st.cache_data.clear()

try:
    invoices = fetch_invoices()
except Exception as e:
    st.error(f'Could not reach backend: {e}')
    st.stop()

if not invoices:
    st.info('No invoices yet. Upload one on the Upload Invoice page.')
    st.stop()

# Summary table
df = pd.DataFrame(invoices)
df['status'] = df['status'].map(lambda s: STATUS_BADGE.get(s, s))
view = df[['filename', 'vendor_name', 'invoice_date', 'total', 'currency', 'status']].copy()
view.columns = ['File', 'Vendor', 'Date', 'Total', 'Currency', 'Status']
st.dataframe(view, width='stretch', hide_index=True)

st.divider()

# Detail view
options = {f"{inv['filename']} - {inv.get('vendor_name') or 'Unknown'}": inv['id'] for inv in invoices}
choice = st.selectbox('Inspect an invoice', list(options.keys()))
invoice_id = options[choice]

detail = fetch_details(invoice_id)

c = st.columns(4)
c[0].metric('Status', detail['status'])
c[1].metric('Vendor', detail.get('vendor_name') or 'Unknown')
c[2].metric('Total', f"{detail.get('currency', '')} {detail.get('total')}" if detail.get('total') else 'Unknown')
c[3].metric('Invoice #', detail.get('invoice_number') or 'Unknown')

if detail.get('error_message'):
    st.error(detail['error_message'])

items = detail.get('line_items') or []
if items:
    st.write('**Line items**')
    st.dataframe(
        [{'Description': it['description'], 'Qty': it['quantity'], 'Unit price': it['unit_price'], 'Amount': it['amount']} for it in items],
        width=True,
        hide_index=True,
    )

# Reprocess button
if st.button('Reprocess this invoice'):
    try:
        requests.post(f'{BACKEND_URL}/invoices/{invoice_id}/reprocess', timeout=10)
        st.cache_data.clear()
        st.success('Reprocessing started - refresh in a few seconds.')
    except Exception as e:
        st.error(f'Failed to reprocess: {e}')

# Journal entry
st.subheader('Journal Entry')
je = fetch_journal_entry(invoice_id)
if je is None:
    st.caption('No journal entry yet. it is created once the invoice is classified.')
else:
    balanced = abs(float(je['total_debit']) - float(je['total_credit'])) <= 0.01
    je_cols = st.columns(3)
    je_cols[0].metric('Entry status', je['status'])
    je_cols[1].metric('Total debit', f"{float(je['total_debit']):,.2f}")
    je_cols[2].metric('Total credit', f"{float(je['total_credit']):,.2f}")
    st.write('Balanced' if balanced else 'Not balanced')

    rows = []
    for ln in je['lines']:
        debit = float(ln['debit_amount'])
        credit = float(ln['credit_amount'])
        rows.append({
            'Account': f"{ln['account_code']} - {ln['account_name']}",
            'Debit': f"{debit:,.2f}" if debit > 0 else '',
            'Credit': f"{credit:,.2f}" if credit > 0 else '',
            'Memo': ln.get('description') or '',
            'Confidence': f"{ln['confidence_score']:.2f}" if ln.get('confidence_score') is not None else '',
        })
    st.dataframe(rows, width=True, hide_index=True)

# Audit trail
st.subheader('Agent audit trail')
logs = fetch_logs(invoice_id)
if not logs:
    st.caption('No agent logs yet.')
else:
    for log in logs:
        conf = f" confidence {log['confidence_score']:.2f}" if log.get('confidence_score') is not None else ''
        dur = f" {log['duration_ms']}ms" if log.get('duration_ms') is not None else ''
        with st.expander(f" {log['agent_name']} -> {log['step_name']}{conf}{dur}"):
            if log.get('reasoning'):
                st.write(log['reasoning'])
            if log.get('error_message'):
                st.error(log['error_message'])