import enum
import os
import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Chart of Accounts', layout='wide')
st.title('Chart of Accounts')
st.caption('The general-ledger accounts the classification agent maps invoice line items against.')

try:
    accounts = requests.get(f'{BACKEND_URL}/chart-of-accounts', timeout=10).json()
except Exception as e:
    st.error(f'Could not load chart of accounts: {e}')
    st.stop()

if not accounts:
    st.info('Chart of accounts is empty.')
    st.stop()

df = pd.DataFrame(accounts)
df = df[['account_code', 'account_name', 'account_type', 'normal_balance', 'description']]
df.columns = ['Code', 'Name', 'Type', 'Normal balance', 'Description']

counts_by_type = df['Type'].value_counts()
strip = st.columns(len(counts_by_type) or 1)
for i, (t, n) in enumerate(counts_by_type.items()):
    strip[i].metric(t, n)

types = sorted(df['Type'].unique().tolist())
selected = st.multiselect('Filter by type', types, default=types)
df = df[df['Type'].isin(selected)]

st.dataframe(df, use_container_width=True, hide_index=True)
st.caption(f'{len(df)} accounts down')