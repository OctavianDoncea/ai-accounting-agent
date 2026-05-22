import os
import time
import requests
import streamlit as st

BACKEND_URL = os.environ.get('BACKEND_URL', 'http://backend:8000')

st.set_page_config(page_title='Upload Invoice', layout='centered')
st.title('Upload Invoice')
st.caption('Upload a PDF or image. The agent will OCR it, extract structured fields, and check for duplicates.')

uploaded = st.file_uploader('Choose an invoice file', type=['pdf', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'webp'])

if uploaded is not None and st.button('Process invoice', type='primary'):
    files = {'file': (uploaded.name, uploaded.getvalue(), uploaded.type or 'application/octet-stream')}
    try:
        resp = requests.post(f'{BACKEND_URL}/invoices/upload', files=files, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        st.error(f'Failed to upload invoice: {e}')
        st.stop()

    invoice_id = resp.json()['invoice_id']
    st.success(f'Uploaded. Invoice ID: `{invoice_id}`')

    # Poll for completion
    terminal = {'EXTRACTED', 'POSTED', 'DUPLICATE', 'NEEDS_REVIEW', 'FAILED'}
    progress = st.progress(0, text='Processing... (OCR -> extraction -> duplicate check)')
    status = 'PENDING'
    detail = None

    for i in range(60):
        time.sleep(1)
        try:
            d = requests.get(f'{BACKEND_URL}/invoices/{invoice_id}', timeout=10).json()
        except Exception:
            continue
        status = d['status']
        detail = d
        progress.progress(min((i + 1) / 20, 1.0), text=f'Status: ({status})')

        if status in terminal:
            break
    progress.empty()

    if detail:
        if status == 'FAILED':
            st.error(detail.get('error_message') or 'Processing failed.')
        else:
            cols = st.columns(2)
            cols[0].metric('Vendor', detail.get('vendor_name') or 'Unknown')
            total = detail.get('total')
            cols[1].metric('Total', f"{detail.get('currency', '')} {total}" if total else 'Unknown')
            cols2 = st.columns(2)
            cols2[0].metric('Invoice #', detail.get('invoice_number') or 'Unknown')
            cols2[1].metric('Invoice date', detail.get('invoice_date') or 'Unknown')

            items = detail.get('line_items') or []
            if items:
                st.write('**Line items**')
                st.dataframe(
                    [
                        {'Description': it['description'], 'Qty': it['quantity'], 'Unit price': it['unit_price'], 'Amount': it['amount']} for it in items
                    ],
                    width='stretch', hide_index=True
                )

        st.caption('See the full agent audit trail ont the Invoices page.')
        st.page_link('pages/2_Invoices.py', label=' Go to Invoices ->')