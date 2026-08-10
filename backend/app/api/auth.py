import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, UserOut
from app.security import get_current_user_email
from app.services.auth_service import AuthError, create_user, authenticate_user, create_access_token

router = APIRouter(prefix='/auth', tags=['auth'])
logger = logging.getLogger(__name__)

@router.post('/signup', response_model=TokenResponse, status_code=201)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = create_user(db, payload.email, payload.password)
    except AuthError as e:
        raise HTTPException(status_code=409, detail=str(e))
    token = create_access_token(user)
    return TokenResponse(access_token=token, email=user.email)

@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = authenticate_user(db, payload.email, payload.password)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    token = create_access_token(user)
    return TokenResponse(access_token=token, email=user.email)

@router.get('/me', response_model=UserOut)
def me(email: str = Depends(get_current_user_email)) -> UserOut:
    return UserOut(email=email)