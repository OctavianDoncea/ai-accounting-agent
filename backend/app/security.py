"""JWT-based auth: a global middleware gates every route except a small allowlist.
"""
import uuid
from fastapi import HTTPException, Request
from jwt import PyJWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from app.config import settings
from app.services.auth_service import decode_access_token

OPEN_PATHS = {'/health', '/', '/auth/signup', '/auth/login'}

def _extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None
    return header[len('Bearer '):]

class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.jwt_secret:
            return await call_next(request)

        if request.url.path in OPEN_PATHS:
            return await call_next(request)

        token = _extract_bearer_token(request)
        if token is None:
            return JSONResponse({'detail': 'Not authenticated.'}, status_code=401)

        try:
            decode_access_token(token)
        except PyJWTError:
            return JSONResponse({'detail': 'Invalid or expired session. Please log in again.'}, status_code=401)

        return await call_next(request)


def get_current_user_email(request: Request) -> str:
    if not settings.jwt_secret:
        raise HTTPException(status_code=400, detail='Auth is not enabled on this server.')

    token = _extract_bearer_token(request)
    if token is None:
        raise HTTPException(status_code=401, detail='Not authenticated.')

    try:
        payload = decode_access_token(token)
    except PyJWTError:
        raise HTTPException(status_code=401, detail='Invalid or expired session. Please log in again.')

    return payload['email']

def get_current_user_id(request: Request) -> uuid.UUID | None:
    if not settings.jwt_secret:
        return None

    token = _extract_bearer_token(request)
    if token is None:
        return None

    try:
        payload = decode_access_token(token)
    except PyJWTError:
        return None

    return uuid.UUID(payload['sub'])