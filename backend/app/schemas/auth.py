"""Schemas for signup/login"""
from pydantic import BaseModel, EmailStr, field_validator

MIN_PASSWORD_LENGTH = 8

class SignupRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator('password')
    @classmethod
    def password_long_enough(cls, v: str) -> str:
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters long')
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    email: str


class UserOut(BaseModel):
    email: str