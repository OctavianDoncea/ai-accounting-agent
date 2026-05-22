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

def fetch_detail(invoice_id):
    return requests.get(f'{BACKEND_URL}/invoices/{invoice_id}', timeout=10).json()

def fetch_logs(invoice_id):
    return requests.get(f'{BACKEND_URL}/invoices/{invoice_id}/logs', timeout=10).json()

col_refresh, _ = st.columns([1, 5])
if col_refresh.button('Refresh'):
    st.cache_data.clear()

try:
    invoices = fetch_invoices()
except Exception as e:
    st.error(f'Could not reach backend: {e}')
    st.stop()

if not invoices:
    st.info('No invoices found. Upload one on the Upload Invoice page.')
    st.stop()

# Summary table
df = pd.DataFrame(invoices)
df['status'] = df['status'].map(lambda s: STATUS_BADGE.get(s, s))
view = df[['filename', 'vendor_name', 'invoice_date', 'total', 'currency', 'status']].copy()
view.columns = ['File', 'Vendor', 'Date', 'Total', 'Currency', 'Status']
st.dataframe(view, width='stretch', hide_index=True)

st.divider()

# Detail view
options = {f"inv['filename'] - {inv.get('vendor_name') or 'unkown'}": inv['id'] for inv in invoices}
choice = st.selectbox('Inspect an invoice', list(options.keys()))
invoice_id = options[choice]

detail = fetch_detail(invoice_id)

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
        width='stretch', hide_index=True
    )

# Reprocess button
if st.button('Reprocess this invoice'):
    try:
        requests.post(f'{BACKEND_URL}/invoices/{invoice_id}/reprocess', timeout=10)
        st.cache_data.clear()
        st.success('Reprocessing started. Refresh to see the updated status.')
    except Exception as e:
        st.error(f'Failed to reprocess: {e}')

# Audit trail
st.subheader('Agent audit trail')
logs = fetch_logs(invoice_id)

if not logs:
    st.caption('No agent logs yet.')
else:
    for log in logs:
        conf = f" confidence{log['confidence_score']:.2f}" if log.get('confidence_score') is not None else ''
        dur = f" {log['duration_ms']}ms" if log.get('duration_ms') is not None else ''
        with st.expander(f"{log['agent_name']} -> {log['step_name']}{conf}{dur}"):
            if log.get('reasoning'):
                st.write(log['reasoning'])
            if log.get('error_message'):
                st.error(log['error_message'])