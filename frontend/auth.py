"""Streamlit auth helpers."""
import json
import os
import time
import requests
import streamlit as st
from streamlit_js_eval import streamlit_js_eval

TOKEN_KEY = 'aaa_access_token'
EMAIL_KEY = 'aaa_user_email'


def _backend_url() -> str:
    return os.environ.get('BACKEND_URL', 'http://backend:8000')


def _auth_headers() -> dict:
    token = st.session_state.get('access_token')
    return {'Authorization': f'Bearer {token}'} if token else {}


def api_get(url: str, **kwargs):
    headers = {**_auth_headers(), **kwargs.pop('headers', {})}
    return requests.get(url, headers=headers, **kwargs)


def api_post(url: str, **kwargs):
    headers = {**_auth_headers(), **kwargs.pop('headers', {})}
    return requests.post(url, headers=headers, **kwargs)

def require_ok(resp: requests.Response) -> requests.Response:
    if resp.status_code == 401:
        _clear_stored_auth(clear_storage=True)
        st.session_state.pop('_auth_storage_ready', None)
        _show_login_form()
        st.stop()
    resp.raise_for_status()
    return resp

def api_get_ok(url: str, *, attempts: int = 3, timeout: float = 45, **kwargs) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = api_get(url, timeout=timeout, **kwargs)
            if resp.status_code == 401:
                return require_ok(resp)
            if resp.status_code >= 500 and attempt < attempts - 1:
                time.sleep(2)
                continue
            return require_ok(resp)
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(2)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError(f'Failed to GET {url}')

def _ls_get(key: str, component_key: str):
    return streamlit_js_eval(
        js_expressions=f'localStorage.getItem({json.dumps(key)})',
        key=component_key,
    )

def _ls_set(key: str, value: str, component_key: str) -> None:
    streamlit_js_eval(
        js_expressions=f'localStorage.setItem({json.dumps(key)}, {json.dumps(value)})',
        key=component_key,
    )

def _ls_remove(key: str, component_key: str) -> None:
    streamlit_js_eval(
        js_expressions=f'localStorage.removeItem({json.dumps(key)})',
        key=component_key,
    )

def _save_auth(token: str, email: str) -> None:
    st.session_state['access_token'] = token
    st.session_state['user_email'] = email
    _ls_set(TOKEN_KEY, token, 'aaa_ls_set_token')
    _ls_set(EMAIL_KEY, email, 'aaa_ls_set_email')

def _clear_stored_auth(*, clear_storage: bool) -> None:
    st.session_state.pop('access_token', None)
    st.session_state.pop('user_email', None)
    if clear_storage:
        _ls_remove(TOKEN_KEY, 'aaa_ls_del_token')
        _ls_remove(EMAIL_KEY, 'aaa_ls_del_email')

def _restore_auth_from_storage() -> None:
    if st.session_state.get('access_token'):
        return

    token = _ls_get(TOKEN_KEY, 'aaa_ls_get_token')
    # JS bridge needs one rerun before the value is available.
    if not st.session_state.get('_auth_storage_ready'):
        st.session_state['_auth_storage_ready'] = True
        st.rerun()

    if not token:
        return

    st.session_state['access_token'] = token
    email = _ls_get(EMAIL_KEY, 'aaa_ls_get_email')
    if email:
        st.session_state['user_email'] = email

def _session_still_valid() -> bool:
    """Return True if the token is valid. Retry transient errors; stop only if still unreachable."""
    if not st.session_state.get('access_token'):
        return False

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            r = api_get(f'{_backend_url()}/auth/me', timeout=30)
        except Exception as exc:
            last_exc = exc
            time.sleep(2)
            continue
        if r.status_code == 401:
            return False
        if r.status_code != 200:
            last_exc = RuntimeError(f'Session check failed ({r.status_code})')
            time.sleep(2)
            continue
        body = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        if body.get('email'):
            st.session_state['user_email'] = body['email']
        return True

    st.error(f'Could not verify session: {last_exc}')
    st.info('The backend may still be waking up. Refresh in a moment.')
    st.stop()

def _show_login_form() -> None:
    st.title('AI Accounting Agent')
    st.caption('Sign in or create an account to continue.')

    login_tab, signup_tab = st.tabs(['Log in', 'Sign up'])

    with login_tab:
        email = st.text_input('Email', key='login_email')
        password = st.text_input('Password', type='password', key='login_password')
        if st.button('Log in', type='primary', key='login_button'):
            _attempt('login', email, password)

    with signup_tab:
        new_email = st.text_input('Email', key='signup_email')
        new_password = st.text_input('Password', type='password', key='signup_password', help='At least 8 characters.')
        if st.button('Create account', type='primary', key='signup_button'):
            _attempt('signup', new_email, new_password)

def _attempt(mode: str, email: str, password: str) -> None:
    if not email or not password:
        st.error('Enter both email and password.')
        return
    try:
        r = requests.post(f'{_backend_url()}/auth/{mode}', json={'email': email, 'password': password}, timeout=30)
    except Exception as e:
        st.error(f'Could not reach the backend: {e}')
        return

    if r.status_code not in (200, 201):
        detail = r.json().get('detail', r.text) if r.headers.get('content-type', '').startswith('application/json') else r.text
        st.error(detail)
        return

    body = r.json()
    _save_auth(body['access_token'], body['email'])
    st.rerun()

def _probe_ready(*, timeout: float = 15) -> dict | None:
    """Hit /ready if available; otherwise fall back to /health with DB check."""
    try:
        r = requests.get(f'{_backend_url()}/ready', timeout=timeout)
        if r.status_code == 200:
            body = r.json()
            if body.get('ready'):
                return body
            return None
        # Older backends without /ready
        if r.status_code == 404:
            return _probe_ready_via_health(timeout=timeout)
    except Exception:
        pass
    return None

def _probe_ready_via_health(*, timeout: float = 15) -> dict | None:
    try:
        r = requests.get(f'{_backend_url()}/health', timeout=timeout)
        r.raise_for_status()
        health = r.json()
        if health.get('database', {}).get('ok'):
            return {
                'ready': True,
                'auth_enabled': bool(health.get('auth_enabled', False)),
                '_health': health,
            }
    except Exception:
        return None
    return None

def _fetch_health(*, timeout: float = 30) -> dict | None:
    try:
        r = requests.get(f'{_backend_url()}/health', timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def wait_for_backend(*, timeout: float = 120) -> dict:
    """Poll until the API (and its database) are ready. Handles Render/Neon cold starts."""
    deadline = time.monotonic() + timeout

    ready_info = _probe_ready(timeout=10)
    if ready_info is None:
        with st.spinner('Connecting to backend (may take up to a minute if it was sleeping)…'):
            while time.monotonic() < deadline:
                ready_info = _probe_ready(timeout=15)
                if ready_info is not None:
                    break
                time.sleep(2)

    if ready_info is None:
        st.error(f'Backend unreachable at `{_backend_url()}`.')
        st.info(
            'On the free Render tier the API sleeps after ~15 minutes idle. '
            'Open the backend URL once to wake it, then refresh this page.'
        )
        st.stop()

    health = ready_info.get('_health') or _fetch_health(timeout=30)
    if health is None:
        health = {
            'database': {'ok': True},
            'ollama': {'ok': False},
            'llm': {'ok': False},
            'auth_enabled': bool(ready_info.get('auth_enabled', False)),
            'status': 'ok',
        }
    else:
        health['auth_enabled'] = bool(
            ready_info.get('auth_enabled', health.get('auth_enabled', False))
        )

    st.session_state['_backend_health'] = health
    return health

def require_login() -> None:
    if st.session_state.pop('_auth_force_logout', False):
        _clear_stored_auth(clear_storage=True)
        health = wait_for_backend()
        if health.get('auth_enabled', False):
            _show_login_form()
            st.stop()
        return

    _restore_auth_from_storage()

    health = wait_for_backend()

    if not health.get('auth_enabled', False):
        return

    if _session_still_valid():
        return

    had_token = bool(st.session_state.get('access_token'))
    _clear_stored_auth(clear_storage=had_token)
    _show_login_form()
    st.stop()

def logout_button() -> None:
    if not st.session_state.get('user_email'):
        return

    with st.sidebar:
        st.caption(f'Signed in as **{st.session_state["user_email"]}**')
        if st.button('Log out'):
            st.session_state['_auth_force_logout'] = True
            st.session_state.pop('_auth_storage_ready', None)
            st.rerun()