import os
import pandas as pd
import streamlit as st
from auth import api_get, api_post, require_login, logout_button

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Reconciliation', layout='wide')
require_login()
logout_button()

st.title('Bank Reconciliation')
st.caption('Upload a bank statement (CSV). The agent matches payments against posted journal entries.')

uploaded = st.file_uploader('Bank statement (CSV)', type=['csv', 'txt'])

if uploaded is not None and st.button('Reconcile', type='primary'):
    files = {'file': (uploaded.name, uploaded.getvalue(), 'text/csv')}
    try:
        resp = api_post(f'{BACKEND_URL}/reconciliation/upload', files=files, timeout=60)
    except Exception as e:
        st.error(f'Upload failed: {e}')
        st.stop()
    if resp.status_code != 201:
        st.error(f"Reconciliation failed: {resp.json().get('detail', resp.text)}")
        st.stop()
    st.session_state['report'] = resp.json()

report = st.session_state.get('report')

if report:
    st.divider()
    m = st.columns(4)
    m[0].metric('Matched', report['matched_count'])
    m[1].metric('Unmatched payments', report['unmatched_bank_count'])
    m[2].metric('Unpaid posted bills', report['unmatched_journal_count'])
    m[3].metric('Total matched', f"{float(report['total_matched_amount']):,.2f}")
    st.caption(report.get('summary') or '')


    if report['matched']:
        st.subheader('Matched payments')
        st.dataframe(
            [{"Date": t["transaction_date"], "Description": t["description"],
              "Amount": f"{float(t['amount']):,.2f}",
              "Confidence": f"{t['match_confidence']:.2f}" if t["match_confidence"] else "",
              "Why": t["match_reasoning"]} for t in report["matched"]],
            width='stretch', hide_index=True,
        )

    if report['unmatched_bank']:
        st.subheader('Payments with no matching invoice')
        st.caption('These left the bank but have no recorded bill: a possible missing invoice.')
        st.dataframe(
            [{"Date": t["transaction_date"], "Description": t["description"],
              "Amount": f"{float(t['amount']):,.2f}", "Note": t["match_reasoning"]}
             for t in report["unmatched_bank"]],
            width='stretch', hide_index=True,
        )

    if report['unmatched_journal']:
        st.subheader('Posted bills with no payment')
        st.caption("Recorder bills that weren't paid in this statement - possibly still outstanding.")
        st.dataframe(
            [{'Vendor': j['vendor_name'], 'Date': j['entry_date'], 'Amount': f"{float(j['amount']):,.2f}"} for j in report["unmatched_journal"]],
            width='stretch', hide_index=True,
        )

    if report['ignored']:
        with st.expander(f"Ignored deposits / inflows ({len(report['ignored'])})"):
            st.dataframe(
                [{"Date": t["transaction_date"], "Description": t["description"],
                  "Amount": f"{float(t['amount']):,.2f}"} for t in report["ignored"]],
                width='stretch', hide_index=True,
            )

st.divider()
st.subheader('Past reconciliation runs')
try:
    runs_resp = api_get(f'{BACKEND_URL}/reconciliation/runs', timeout=10)
    runs_resp.raise_for_status()
    runs = runs_resp.json()
    if runs:
        df = pd.DataFrame(runs)[['created_at', 'filename', 'matched_count', 'unmatched_bank_count', 'unmatched_journal_count', 'total_matched_amount']]
        df.columns = ['When', 'File', 'Matched', 'Unmatched payments', 'Unpaid bills', 'Matched total']
        st.dataframe(df, width='stretch', hide_index=True)
    else:
        st.caption('No reconciliation runs yet.')
except Exception as e:
    st.caption(f'Could not load past runs: {e}')