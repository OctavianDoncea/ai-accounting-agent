import os
from datetime import datetime, timedelta, timezone
import extra_streamlit_components as stx
import requests
import streamlit as st

TOKEN_COOKIE = 'aaa_access_token'
EMAIL_COOKIE = 'aaa_user_email'
COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


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


def _save_auth(token: str, email: str, cm: stx.CookieManager) -> None:
    st.session_state['access_token'] = token
    st.session_state['user_email'] = email
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=COOKIE_MAX_AGE_SECONDS)
    cm.set(
        TOKEN_COOKIE, token,
        key='aaa_set_token',
        expires_at=expires_at,
        max_age=COOKIE_MAX_AGE_SECONDS,
        same_site='lax',
    )
    cm.set(
        EMAIL_COOKIE, email,
        key='aaa_set_email',
        expires_at=expires_at,
        max_age=COOKIE_MAX_AGE_SECONDS,
        same_site='lax',
    )


def _delete_auth_cookies(cm: stx.CookieManager) -> None:
    cm.delete(TOKEN_COOKIE, key='aaa_delete_token')
    cm.delete(EMAIL_COOKIE, key='aaa_delete_email')

def _restore_auth_from_cookies(cm: stx.CookieManager) -> None:
    if st.session_state.get('access_token'):
        return

    token = cm.get(TOKEN_COOKIE) or st.context.cookies.get(TOKEN_COOKIE)
    if not token:
        return

    st.session_state['access_token'] = token
    email = cm.get(EMAIL_COOKIE) or st.context.cookies.get(EMAIL_COOKIE)
    if email:
        st.session_state['user_email'] = email

def _session_still_valid() -> bool:
    if not st.session_state.get('access_token'):
        return False
    try:
        r = api_get(f'{_backend_url()}/auth/me', timeout=5)
    except Exception:
        return False
    if r.status_code != 200:
        return False
    body = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
    if body.get('email'):
        st.session_state['user_email'] = body['email']
    return True

def _show_login_form(cm: stx.CookieManager) -> None:
    st.title('AI Accounting Agent')
    st.caption('Sign in or create an account to continue.')

    login_tab, signup_tab = st.tabs(['Log in', 'Sign up'])

    with login_tab:
        email = st.text_input('Email', key='login_email')
        password = st.text_input('Password', type='password', key='login_password')
        if st.button('Log in', type='primary', key='login_button'):
            _attempt('login', email, password, cm)

    with signup_tab:
        new_email = st.text_input('Email', key='signup_email')
        new_password = st.text_input('Password', type='password', key='signup_password', help='At least 8 characters.')
        if st.button('Create account', type='primary', key='signup_button'):
            _attempt('signup', new_email, new_password, cm)

def _attempt(mode: str, email: str, password: str, cm: stx.CookieManager) -> None:
    if not email or not password:
        st.error('Enter both email and password.')
        return
    try:
        r = requests.post(f'{_backend_url()}/auth/{mode}', json={'email': email, 'password': password}, timeout=10)
    except Exception as e:
        st.error(f'Could not reach the backend: {e}')
        return

    if r.status_code not in (200, 201):
        detail = r.json().get('detail', r.text) if r.headers.get('content-type', '').startswith('application/json') else r.text
        st.error(detail)
        return

    body = r.json()
    _save_auth(body['access_token'], body['email'], cm)
    st.rerun()

def _auth_enabled() -> bool:
    try:
        health = requests.get(f'{_backend_url()}/health', timeout=3).json()
    except Exception:
        return False

    return bool(health.get('auth_enabled', False))

def require_login() -> None:
    cm = stx.CookieManager(key='aaa_auth_cookies')

    if not _auth_enabled():
        return

    if st.session_state.pop('_auth_force_logout', False):
        st.session_state.pop('access_token', None)
        st.session_state.pop('user_email', None)
        st.session_state.pop('_auth_cookies_ready', None)
        _delete_auth_cookies(cm)
        _show_login_form(cm)
        st.stop()

    _restore_auth_from_cookies(cm)

    if not st.session_state.get('access_token') and not st.session_state.get('_auth_cookies_ready'):
        st.session_state['_auth_cookies_ready'] = True
        st.rerun()

    _restore_auth_from_cookies(cm)

    if _session_still_valid():
        return

    had_token = bool(st.session_state.get('access_token'))
    st.session_state.pop('access_token', None)
    st.session_state.pop('user_email', None)
    if had_token:
        _delete_auth_cookies(cm)

    _show_login_form(cm)
    st.stop()

def logout_button() -> None:
    if not st.session_state.get('user_email'):
        return

    with st.sidebar:
        st.caption(f'Signed in as **{st.session_state["user_email"]}**')
        if st.button('Log out'):
            st.session_state.pop('access_token', None)
            st.session_state.pop('user_email', None)
            st.session_state['_auth_force_logout'] = True
            st.session_state.pop('_auth_cookies_ready', None)
            st.rerun()