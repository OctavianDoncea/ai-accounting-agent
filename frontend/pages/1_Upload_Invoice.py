import json
import os
import requests
import streamlit as st
from auth import api_get, api_post, require_login, logout_button, stream_url
from ui_helpers import INVOICE_STATUS_BADGE, format_money

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Upload Invoice', layout='centered')
require_login()
logout_button()

st.title('Upload Invoice')
st.caption('Upload a PDF or image. The agent will OCR it, extract structured fields, and check for duplicates.')

uploaded = st.file_uploader('Choose an invoice file', type=['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'webp', 'heic', 'heif'])

if uploaded is not None and st.button('Process invoice', type='primary'):
    files = {'file': (uploaded.name, uploaded.getvalue(), uploaded.type or 'application/octet-stream')}
    try:
        resp = api_post(f'{BACKEND_URL}/invoices/upload', files=files, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        st.error(f'Failed to upload invoice: {e}')
        st.stop()

    invoice_id = resp.json()['invoice_id']
    st.success(f'Uploaded. Invoice ID: `{invoice_id}`')

    terminal = {'POSTED', 'DUPLICATE', 'NEEDS_REVIEW', 'FAILED'}
    step_labels = {
        'extract_text': '1/5 OCR',
        'extract_fields': '2/5 Extracting fields',
        'check_duplicate': '3/5 Checking duplicates',
        'classify_line_items': '4/5 Classifying accounts',
        'apply_vendor_memory': '4/5 Applying vendor memory',
        'build_entry': '4/5 Building journal entry',
        'validate_entry': '5/5 Validating entry',
        'final_status': 'Done',
    }
    progress = st.progress(0, text='Starting')
    status_box = st.empty()

    detail = None
    status = 'PENDING'

    def _consume_stream():
        """Yield parsed progress dicts from the SSE endpoint until it closes."""
        url = stream_url(f'{BACKEND_URL}/invoices/{invoice_id}/stream')
        with requests.get(url, stream=True, timeout=310) as r:
            r.raise_for_status()
            event_type = None
            for raw in r.iter_lines(decode_unicode=True):
                if raw is None or raw == '':
                    event_type = None
                    continue
                if raw.startswith('event:'):
                    event_type = raw[len('event:'):].strip()
                elif raw.startswith('data:'):
                    payload = raw[len('data:'):].strip()
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    yield event_type or 'progress', data

    try:
        for event_type, data in _consume_stream():
            status = data.get('status', status)
            if event_type in ('progress', 'done'):
                last_step = data.get('last_step')
                steps_done = data.get('steps_done', 0)
                if last_step:
                    label = step_labels.get(last_step, last_step)
                    progress.progress(min(steps_done / 7, 1.0), text=label)
                    status_box.caption(f'Latest: {data.get("last_agent")}: {last_step}')
            if event_type in ('done', 'timeout', 'error') or status in terminal:
                break
    except Exception:
        try:
            status = api_get(f'{BACKEND_URL}/invoices/{invoice_id}', timeout=10).json()['status']
        except Exception:
            pass

    progress.empty()
    status_box.empty()

    try:
        detail = api_get(f'{BACKEND_URL}/invoices/{invoice_id}', timeout=10).json()
        status = detail['status']
    except Exception:
        detail = None

    # Final results
    badge = INVOICE_STATUS_BADGE.get(status, status)
    if status == 'POSTED':
        st.success(f'{badge}: journal entry created and posted.')
    elif status == 'FAILED':
        st.error(f'{badge}')
        if detail and detail.get('error_message'):
            st.caption(detail['error_message'])
    elif status == 'DUPLICATE':
        st.info(f'{badge}: this invoice matched an existing one.')
    elif status == 'NEEDS_REVIEW':
        st.info(f'{badge}: see Invoices page for details.')
    else:
        st.info(f'{badge}')

    if detail and status != 'FAILED':
        cols = st.columns(2)
        cols[0].metric('Vendor', detail.get('vendor_name') or '-')
        cols[1].metric('Total', format_money(detail.get('total'), detail.get('currency', '')))
        cols2 = st.columns(2)
        cols2[0].metric('Invoice #', detail.get('invoice_number') or '-')
        cols2[1].metric('Invoice date', detail.get('invoice_date') or '-')

        items = detail.get('line_items') or []
        if items:
            st.write('Line items')
            st.dataframe([
                {'Description': it['description'], 'Qty': it['quantity'], "Unit price": format_money(it['unit_price']), 'Amount': format_money(it['amount'])}
                for it in items
            ], width='stretch', hide_index=True)

        st.page_link('pages/2_Invoices.py', label='See full details and audit trail')