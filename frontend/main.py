import os
import pandas as pd
import requests
import streamlit as st
from ui_helpers import format_money, format_date, INVOICE_STATUS_BADGE
from auth import api_get, api_post, require_login, logout_button

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='AI Accounting Agent', layout='wide')
require_login()
logout_button()

# Header
st.title('AI Accounting Agent')
st.caption('Automated invoice ingestion, classification, and reconciliation, powered by local LLM agents.')

# System status
try:
    with st.spinner('Connecting to backend (may take up to a minute if it was sleeping)…'):
        health = requests.get(f'{BACKEND_URL}/health', timeout=90).json()
    db_ok = health['database']['ok']
    ollama_ok = health['ollama']['ok']
except Exception as e:
    st.error(f'Backend unreachable at `{BACKEND_URL}`: {e}')
    st.info('On the free Render tier the API sleeps after ~15 minutes idle. Open the backend URL once to wake it, then refresh this page.')
    st.stop()  

status_cols = st.columns([1, 1, 6])
status_cols[0].markdown(f"**Database**  \n{'Online' if db_ok else 'Offline'}")
status_cols[1].markdown(f"**LLM**  \n{'Online' if ollama_ok else 'Offline'}")

if not ollama_ok:
    status_cols[2].caption("LLM isn't reachable. Invoice processing will fail until it's running.")

st.divider()

# Summary metrics
try:
    summary = requests.get(f"{BACKEND_URL}/dashboard/summary", timeout=5).json()
except Exception as exc:
    st.error(f"Could not load dashboard: {exc}")
    st.stop()

m = st.columns(4)
m[0].metric("Invoices processed", summary["total_invoices"])
m[1].metric("Journal entries posted", summary["journal_entries_posted"])
m[2].metric("Total posted value", format_money(summary["total_posted_value"]))
m[3].metric("Reconciliation runs", summary["reconciliation_runs"])

# Optional sub-stats row
counts = summary["invoice_counts"]
needs_review = counts.get("NEEDS_REVIEW", 0)
draft = summary["journal_entries_draft"]
if needs_review or draft or counts.get("FAILED"):
    sub = st.columns(4)
    if needs_review:
        sub[0].warning(f"**{needs_review}** invoice(s) need review")
    if draft:
        sub[1].warning(f"**{draft}** draft journal entr{'y' if draft == 1 else 'ies'}")
    if counts.get("FAILED"):
        sub[2].error(f"**{counts['FAILED']}** failed invoice(s)")
    if counts.get("DUPLICATE"):
        sub[3].info(f"**{counts['DUPLICATE']}** duplicate(s)")

st.divider()

# Two-column: recent invoices + recent reconciliation runs
left, right = st.columns(2)

with left:
    st.subheader("Recent invoices")
    if not summary["recent_invoices"]:
        st.caption("No invoices yet. Try the Upload Invoice page.")
    else:
        df = pd.DataFrame([
            {
                "File": inv["filename"],
                "Vendor": inv["vendor_name"] or "-",
                "Total": format_money(inv["total"], inv["currency"]) if inv["total"] else "-",
                'Status': INVOICE_STATUS_BADGE.get(inv["status"], inv["status"])
            }
            for inv in summary["recent_invoices"]
        ])
        st.dataframe(df, width='stretch', hide_index=True)
    st.page_link("pages/2_Invoices.py", label="View all invoices ->")

with right:
    st.subheader("Recent reconciliations")
    if not summary["recent_runs"]:
        st.caption("No reconciliation runs yet. Try the Reconciliation page.")
    else:
        df = pd.DataFrame([
            {
                "When": format_date(r["created_at"]),
                "File": r["filename"],
                "Matched": r["matched_count"],
                "Unmatched": r["unmatched_bank_count"],
                "Unpaid": r["unmatched_journal_count"],
                "Total matched": format_money(r["total_matched_amount"]),
            }
            for r in summary["recent_runs"]
        ])
        st.dataframe(df, width='stretch', hide_index=True)
    st.page_link("pages/4_Reconciliation.py", label="Go to Reconciliation →")

st.divider()

# Quick actions
st.subheader("Quick actions")
qa = st.columns(5)
with qa[0]:
    st.page_link("pages/1_Upload_Invoice.py", label="⬆Upload an invoice")
with qa[1]:
    st.page_link("pages/4_Reconciliation.py", label="Reconcile statement")
with qa[2]:
    st.page_link("pages/7_Review.py", label="Review flagged invoices")
with qa[3]:
    st.page_link("pages/6_Reports.py", label="View reports")
with qa[4]:
    st.page_link('pages/5_Chart_of_Accounts.py', label='Chart of accounts')