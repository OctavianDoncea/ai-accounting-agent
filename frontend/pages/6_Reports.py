import os
import pandas as pd
import streamlit as st
from auth import api_get, require_login, logout_button
from ui_helpers import format_money

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Reports', layout='wide')
require_login()
logout_button()

st.title('Accounting Reports')
st.caption('Reports derived from posted journal entries.')

# Trial balance
st.subheader('Trial Balance')
st.caption('Sum of debits and credits per active account. In a healthy ledger, the totals match.')

try:
    tb_resp = api_get(f'{BACKEND_URL}/reports/trial-balance', timeout=10)
    tb_resp.raise_for_status()
    tb = tb_resp.json()
except Exception as e:
    st.error(f'Could not load trial balance: {e}')
    st.stop()

if not tb['rows']:
    st.info('Nothing posted yet, no balance to show')
else:
    rows = []
    for r in tb['rows']:
        rows.append({
            'Code': r['account_code'],
            'Account': r['account_name'],
            'Type': r['account_type'],
            'Debits': format_money(r['total_debits']),
            'Credits': format_money(r['total_credits']),
            'Balance': format_money(r['balance']),
            'Normal': r['normal_balance']
        })
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)

    tb_cols = st.columns(3)
    tb_cols[0].metric('Total debits', format_money(tb['total_debits']))
    tb_cols[1].metric('Total credits', format_money(tb['total_credits']))
    tb_cols[2].metric('Balanced', "Yes" if tb['is_balanced'] else 'No')

st.divider()

# Expense breakdown chart
st.subheader('Spending by category')
st.caption('Total debited to each expense account from posted entries.')

try:
    breakdown_resp = api_get(f'{BACKEND_URL}/reports/expense-breakdown', timeout=10)
    breakdown_resp.raise_for_status()
    breakdown = breakdown_resp.json()
except Exception as e:
    st.error(f'Could not load expense breakdown: {e}')
    st.stop()

if not breakdown:
    st.info('No expenses posted yet')
else:
    df = pd.DataFrame([
        {'Account': f"{r['account_code']} - {r['account_name']}", 'Total': float(r['total'])}
        for r in breakdown
    ])

    st.bar_chart(df.set_index('Account'))
    st.caption(f'Total expense activity: **{format_money(df["Total"].sum())}**')

    with st.expander('View as table'):
        df_display = df.copy()
        df_display['Total'] = df_display['Total'].map(format_money)
        st.dataframe(df_display, width='stretch', hide_index=True)

st.divider()

# Accounts payable aging
st.subheader('Accounts Payable aging')
st.caption("Posted bills that have not been paid yet, grouped by how long they have been outstanding. A bill counts as paid once reconciliation matches a bank payment to it.")

try:
    aging_resp = api_get(f'{BACKEND_URL}/reports/ap-aging', timeout=10)
    aging_resp.raise_for_status()
    aging = aging_resp.json()
except Exception as e:
    st.error(f'Could not load AP aging: {e}')
    aging = None

if aging is not None:
    if not aging['rows']:
        st.success('Nothing outstanding. Every posted bill has been paid, or there are no bills yet.')
    else:
        bucket_cols = st.columns(len(aging['buckets']) + 1)
        bucket_labels = {'0-30': '0-30 days', '31-60': '31-60 days', '61-90': '61-90 days', '90+': '90+ days'}
        for i, b in enumerate(aging['buckets']):
            bucket_cols[i].metric(bucket_labels.get(b['bucket'], b['bucket']), format_money(b['total']), f"{b['count']} bill(s)")
        bucket_cols[-1].metric('Total outstanding', format_money(aging['total_outstanding']))

        aging_rows = []
        for r in aging['rows']:
            aging_rows.append({
                'Vendor': r['vendor_name'],
                'Invoice #': r['invoice_number'] or '-',
                'Entry date': r['entry_date'],
                'Days outstanding': r['days_outstanding'],
                'Bucket': bucket_labels.get(r['bucket'], r['bucket']),
                'Amount': format_money(r['amount']),
            })
        st.dataframe(pd.DataFrame(aging_rows), width='stretch', hide_index=True)

st.divider()

# Vendor memory
st.subheader('Vendor memory')
st.caption("Which GL account each vendor's invoices have been posted to, and how many times. The system uses this history to correct uncertain classifications.")

try:
    vendors_resp = api_get(f'{BACKEND_URL}/reports/vendor-memory', timeout=10)
    vendors_resp.raise_for_status()
    vendors = vendors_resp.json()
except Exception as e:
    st.error(f'Could not load vendor memory: {e}')
    vendors = None

if vendors is not None:
    if not vendors:
        st.info('No vendor history yet. Once invoices post, the accounts they classify into are remembered here.')
    else:
        vrows = []
        for v in vendors:
            accounts_str = ', '.join(f"{a['account_code']} (x{a['times_seen']})" for a in v['accounts'])
            vrows.append({
                'Vendor': v['vendor'],
                'Invoices posted': v['total_posts'],
                'Learned account(s)': accounts_str,
            })
        st.dataframe(pd.DataFrame(vrows), width='stretch', hide_index=True)
        st.caption(f'**{len(vendors)}** vendor(s) learned so far.')