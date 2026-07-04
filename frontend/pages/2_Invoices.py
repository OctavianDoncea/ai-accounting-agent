import os
import pandas as pd
import requests
import streamlit as st
from ui_helpers import INVOICE_STATUS_BADGE, JE_STATUS_BADGE, format_money, format_date

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Invoices', layout='wide')
st.title('Invoices')

@st.cache_data(ttl=3)
def fetch_invoices():
    return requests.get(f'{BACKEND_URL}/invoices', timeout=10).json()

def fetch_details(invoice_id):
    return requests.get(f'{BACKEND_URL}/invoices/{invoice_id}', timeout=10).json()

def fetch_logs(invoice_id):
    return requests.get(f'{BACKEND_URL}/invoices/{invoice_id}/logs', timeout=10).json()

def fetch_journal_entry(invoice_id):
    r = requests.get(f'{BACKEND_URL}/invoices/{invoice_id}/journal-entry', timeout=10)
    return None if r.status_code == 404 else r.json()

def fetch_payment_entry(invoice_id):
    r = requests.get(f'{BACKEND_URL}/invoices/{invoice_id}/payment-entry', timeout=10)
    return None if r.status_code == 404 else r.json()

# Top bar
top = st.columns([1, 4])
if top[0].button('Refresh'):
    st.cache_data.clear()

try:
    invoices = fetch_invoices()
except Exception as e:
    st.error(f'Could not reach backend: {e}')
    st.stop()

if not invoices:
    st.info('No invoices yet. Upload one on the Upload Invoice page.')
    st.stop()

# Status filter
all_statuses = sorted({inv['status'] for inv in invoices})
selected_statuses = top[1].multiselect('Filter by status', all_statuses, default=all_statuses, label_visibility='collapsed')
filtered = [inv for inv in invoices if inv['status'] in selected_statuses]

# Status-count strip
status_counts = {s: sum(1 for inv in invoices if inv['status'] == s) for s in all_statuses}
strip = st.columns(min(len(status_counts), 7) or 1)
for i, (s, n) in enumerate(status_counts.items()):
    strip[i % len(strip)].metric(INVOICE_STATUS_BADGE.get(s, s), n)

st.divider()

# Summary table
df = pd.DataFrame([
    {
        'File': inv['filename'],
        'Vendor': inv['vendor_name'] or '-',
        'Date': format_date(inv['invoice_date']),
        'Total': format_money(inv['total'], inv['currency']) if inv['total'] else '-',
        'Status': INVOICE_STATUS_BADGE.get(inv['status'], inv['status'])
    } for inv in filtered
])
st.dataframe(df, width='stretch', hide_index=True)

if not filtered:
    st.stop()

st.divider()

# Detail view
st.subheader('Inspect an invoice')
options = {f"{inv['filename']} {inv.get('vendor_name') or 'unknown'} ({inv['status']})": inv['id'] for inv in filtered}
choices = st.selectbox('Pick one', list(options.keys()), label_visibility='collapsed')
invoice_id = options[choices]
detail = fetch_details(invoice_id)

c = st.columns(4)
c[0].metric('Status', INVOICE_STATUS_BADGE.get(detail['status'], detail['status']))
c[1].metric('Vendor', detail.get('vendor_name') or 'Unknown')
c[2].metric('Total', format_money(detail.get('total'), detail.get('currency')))
c[3].metric('Invoice #', detail.get('invoice_number') or 'Unknown')

if detail.get('error_message'):
    st.error(detail['error_message'])

items = detail.get('line_items') or []
if items:
    st.write('**Line items**')
    st.dataframe(
        [{'Description': it['description'], 'Qty': it['quantity'], 'Unit price': format_money(it['unit_price']), 'Amount': format_money(it['amount'])} for it in items],
        width='stretch', hide_index=True
    )

# Action buttons
act = st.columns(3)
if act[0].button('Reprocess (full pipeline)'):
    try:
        requests.post(f'{BACKEND_URL}/invoices/{invoice_id}/reprocess', timeout=10)
        st.cache_data.clear()
        st.success('Reprocessing started. Refresh in a few seconds.')
    except Exception as e:
        st.error(f'Request failed: {e}')
if act[1].button('Re-classify only'):
    try:
        requests.post(f'{BACKEND_URL}/invoices/{invoice_id}/reclassify', timeout=10)
        st.cache_data.clear()
        st.success('Re-classification started. Refresh in a few seconds.')
    except Exception as e:
        st.error(f'Re-classify failed: {e}')

# Journal entry
st.subheader('Journal entry')
je = fetch_journal_entry(invoice_id)
if je is None:
    st.caption('No journal entry yet; created once the invoice is classified.')
else:
    balanced = abs(float(je['total_debit']) - float(je['total_credit'])) <= 0.01
    je_cols = st.columns(3)
    je_cols[0].metric('Entry status', JE_STATUS_BADGE.get(je['status'], je['status']))
    je_cols[1].metric('Total debit', format_money(je['total_debit']))
    je_cols[2].metric('Total credit', format_money(je['total_credit']))
    st.caption('Balanced' if balanced else 'Not balanced')

    rows = []
    for ln in je['lines']:
        debit = float(ln['debit_amount'])
        credit = float(ln['credit_amount'])
        rows.append({
            'Account': f"{ln['account_code']} {ln['account_name']}",
            'Debit': format_money(debit) if debit > 0 else '',
            'Credit': format_money(credit) if credit > 0 else '',
            'Memo': ln.get('description') or '',
            'Confidence': f"{ln['confidence_score']:.2f}" if ln.get('confidence_score') is not None else ''
        })
    st.dataframe(rows, width='stretch', hide_index=True)

# Payment status
st.subheader('Payment')
payment = fetch_payment_entry(invoice_id)
if payment is None:
    st.caption('Not yet matched to a bank payment. Run reconciliation once the statement is available.')
else:
    pay_cols = st.columns(3)
    pay_cols[0].metric('Payment status', JE_STATUS_BADGE.get(payment['status'], payment['status']))
    pay_cols[1].metric('Amount cleared', format_money(payment['total_credit']))
    pay_cols[2].metric('Payment date', format_date(payment['entry_date']))
    st.success('Accounts Payable cleared. This invoice has been paid and reconciled against the bank statement.')

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