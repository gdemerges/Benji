"""/v1/auth/* — inscription et délivrance de jetons (JWT réel)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.config import ACCESS_TTL_SECONDS
from app.db import Database
from app.deps import get_db
from app.errors import ApiError
from app.plans import DEFAULT_PLAN
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter()


def _tokens(user_id: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        expires_in=ACCESS_TTL_SECONDS,
    )


@router.post("/v1/auth/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: Database = Depends(get_db)) -> TokenResponse:
    if not req.email or not req.password:
        raise ApiError("bad_request", "email et password requis.", 400)
    try:
        user = db.create_user(req.email, hash_password(req.password), plan=DEFAULT_PLAN)
    except sqlite3.IntegrityError as e:
        raise ApiError("bad_request", "Email déjà utilisé.", 400) from e
    return _tokens(user["id"])


@router.post("/v1/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: Database = Depends(get_db)) -> TokenResponse:
    user = db.get_user_by_email(req.email)
    if user is None or not verify_password(req.password, user["password_hash"]):
        raise ApiError("unauthenticated", "Identifiants invalides.", 401)
    return _tokens(user["id"])


@router.post("/v1/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: Database = Depends(get_db)) -> TokenResponse:
    user_id = decode_token(req.refresh_token, "refresh")
    if user_id is None or db.get_user(user_id) is None:
        raise ApiError("unauthenticated", "refresh_token invalide ou expiré.", 401)
    return _tokens(user_id)
