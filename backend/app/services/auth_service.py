import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from app.config import settings
from app.models.user import User

JWT_ALGORITHM = 'HS256'

class AuthError(ValueError):
    """Raised for any signup/login failure"""


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_user(db: Session, email: str, password: str) -> User:
    email = email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()

    if existing is not None:
        raise AuthError('An account with this email already exists.')

    user = User(email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return user

def authenticate_user(db: Session, email: str, password: str) -> User:
    email = email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError('Incorrect email or password.')
    
    return user

def create_access_token(user: User) -> str:
    if not settings.jwt_secret:
        raise AuthError('Auth is not enabled on this server.')

    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user.id),
        'email': user.email,
        'iat': now,
        'exp': now + timedelta(hours=settings.jwt_expire_hours)
    }

    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM])