import os
import pandas as pd
import requests
import streamlit as st

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='AI Accounting Agent', layout='wide')
st.title('AI Accounting Agent')
st.divider()
st.subheader('System status')

try:
    resp = requests.get(f'{BACKEND_URL}/health', timeout=5)
    resp.raise_for_status()
    health = resp.json()
except Exception as e:
    st.error(f'Backend unreachable at `{BACKEND_URL}`: {e}')
    st.stop()

col1, col2, col3 = st.columns(3)

with col1:
    if health['database']['ok']:
        st.success('Database OK')
        st.caption(f"Accounts seeded: **{health['database']['chart_of_accounts_count']}**")
    else:
        st.error('Database down')
        st.caption(health['database'].get('error') or '')

with col2:
    if health['ollama']['ok']:
        st.success('Ollama OK')
        st.caption(f"Model: `{health['ollama']['model']}`")
    else:
        st.warning('Ollama unreachable')
        st.caption(f"URL: `{health['ollama']['url']}`")

with col3:
    if health['status'] == 'ok':
        st.success('Overall: OK')
    else:
        st.warning(f"Overall: {health['status']}")

st.divider()

st.subheader('Chart of Accounts')
st.caption('Seeded automatically on backend startup. This is the GL the agents will classify against.')

try:
    resp = requests.get(f'{BACKEND_URL}/chart-of-accounts', timeout=5)
    resp.raise_for_status()
    accounts = resp.json()
except Exception as e:
    st.error(f'Could not load chart of accounts: {e}')
    st.stop()

if not accounts:
    st.info('Chart of accounts is empty.')
else:
    df = pd.DataFrame(accounts)
    df = df[['account_code', 'account_name', 'account_type', 'normal_balance', 'description']]
    df.columns = ['Code', 'Name', 'Type', 'Normal balance', 'Description']

    types = sorted(df['Type'].unique().tolist())
    selected = st.multiselect('Filter by account type', types, default=types)
    df = df[df['Type'].isin(selected)]

    st.dataframe(df, width='stretch', hide_index=True)
    st.caption(f'{len(df)} accounts shown')