import os
import requests
import streamlit as st
from ui_helpers import format_money

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Review', layout='wide')
st.title('Manual Review')
st.caption("Invoices the pipeline couldn't safely auto-post: low extraction confidence, a missing vendor, an unbalanced entry, "
    'or a fallback account being used. Pick the correct GL account per line item below. This goes through the same builder and validator the automated path uses.'    
)

@st.cache_data(ttl=3)
def fetch_invoices():
    return requests.get(f'{BACKEND_URL}/invoices').json()

def fetch_review_detail(invoice_id):
    r = requests.get(f'{BACKEND_URL}/invoices/{invoice_id}/review', timeout=10)
    r.raise_for_status()
    return r.json()

top = st.columns([1, 5])
if top[0].button('Refresh'):
    st.cache_data.clear()

try:
    invoices = fetch_invoices()
except Exception as e:
    st.error(f'Could not reach backend: {e}')
    st.stop()

needs_review = [inv for inv in invoices if inv['status'] == 'NEEDS_REVIEW']

if not needs_review:
    st.success('Nothing needs review right now. Every processed invoices is posted, a duplicate, or still in flight.')
    st.stop()

st.info(f'{len(needs_review)} invoice(s) need your input.')

options = {f"{inv['filename']}, {inv.get('vendor_name') or 'unknown vendor'}": inv['id'] for inv in needs_review}
choice = st.selectbox('Pick an invoice to review', list(options.keys()))
invoice_id = options[choice]

try:
    detail = fetch_review_detail(invoice_id)
except Exception as e:
    st.error(f'Could not load review detail: {e}')
    st.stop()

# Invoice summary
c = st.columns(4)
c[0].metric('Vendor', detail['vendor_name'] or ' (missing below)')
c[1].metric('Total', format_money(detail['total'], detail['currency']))
c[2].metric('Tax', format_money(detail['tax'], detail['currency']) if detail['tax'] else ' ')
c[3].metric('Invoice #', detail['invoice_number'] or ' ')

if detail['validation_errors']:
    st.warning('Current draft entry is invalid: ' + '; '.join(detail['validation_errors']))

if not detail['vendor_name']:
    st.warning('This invoice has no vendor name on file. Classification will still work, but consider checking the source PDF. A missing vendor usually means the OCR text was unusual.')

st.divider()

# Account picker per line item
st.subheader('Classify each line item')

account_options = {f"{a['account_code']} {a['account_name']}": a['account_code'] for a in detail['classifiable_accounts']}
option_labels = list(account_options.keys())

def _label_for_code(code: str | None) -> str | None:
    if not code:
        return None
    for label, c in account_options.items():
        if c == code:
            return label
    return None

overrides = []
for li in  detail['line_items']:
    cols = st.columns([3, 1, 1, 2])
    cols[0].markdown(f'{li["description"]}')
    cols[1].caption(f'Qty: {li["quantity"]}')
    cols[2].caption(format_money(li['amount'], detail['currency']))

    default_label = _label_for_code(li['current_account_code'])
    default_index = option_labels.index(default_label) if default_label in option_labels else 0
    selected = cols[3].selectbox('Account', option_labels, index=default_index, key=f'line_{li["line_id"]}', label_visibility='collapsed')
    overrides.append({'line_id': li['line_id'], 'account_code': account_options[selected]})

# Tax account
tax_account_code = None
if detail['tax']:
    st.write('Sales tax')
    tax_cols = st.columns([3, 1, 1, 2])
    tax_cols[0].markdown('Sales tax')
    tax_cols[2].caption(format_money(detail['tax'], detail['currency']))
    default_tax_label = _label_for_code(detail['current_tax_account_code']) or _label_for_code('6920')
    default_tax_index = option_labels.index(default_tax_label) if default_tax_label in option_labels else 0
    tax_selected = tax_cols[3].selectbox('Tax account', option_labels, index=default_tax_index, key='tax_account', label_visibility='collapsed')
    tax_account_code = account_options[tax_selected]

st.divider()

if st.button('Approve and post', type='primary'):
    payload = {'overrides': overrides, 'tax_account_code': tax_account_code}
    try:
        r = requests.post(f'{BACKEND_URL}/invoices/{invoice_id}/review', json=payload, timeout=15)
    except Exception as e:
        st.error(f'Request failed: {e}')
        st.stop()

    if r.status_code != 200:
        st.error(f'Review failed: {r.json().get("detail", r.text)}')
        st.stop()

    result = r.json()
    st.cache_data.clear()
    if result['is_balanced']:
        st.success(f"Posted! Invoice status: {result['invoice_status']}, entry status: {result['journal_entry_status']}.")
        st.balloons()
    else:
        st.warning("Entry still doesn't balance after your review. This usually means the extracted invoice total itself is wrong, which account "
            f"reclassification can't fix. Errors: {'; '.join(result['validation_errors'])}"
        )
    st.page_link('pages/2_Invoices.py', label='View the posted invoice')