import os
import pandas as pd
import requests
import streamlit as st
from ui_helpers import format_money

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Reports', layout='wide')
st.title('Accounting Reports')
st.caption('Reports derived from posted journal entries.')

# Trial balance
st.subheader('Trial Balance')
st.caption('Sum of debits and credits per active account. In a healthy ledger, the totals match.')

try:
    tb = requests.get(f'{BACKEND_URL}/reports/trial-balance', timeout=10).json()
except Exception as e:
    st.error(f'Could not load trial balance: {e}')
    st.stop()

if not tb['rows']:
    st.info('Nothing posted yet, no balance to show')
else:
    rows = []
    for r in tb['rows']:
        rows.append({
            'Code': r['account_type'],
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
    breakdown = requests.get(f'{BACKEND_URL}/reports/expense-breakdown', timeout=10).json()
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