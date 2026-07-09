"""/v1/auth/* — inscription et délivrance de jetons (JWT réel)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from app.config import ACCESS_TTL_SECONDS
from app.db import Database
from app.deps import get_db
from app.errors import ApiError
from app.plans import DEFAULT_PLAN
from app.ratelimit import rate_limit_auth
from app.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from app.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh,
    hash_password,
    verify_password,
)

router = APIRouter(dependencies=[Depends(rate_limit_auth)])


def _issue_tokens(db: Database, user_id: str) -> TokenResponse:
    """Émet un couple access/refresh et persiste le refresh (jti + expiration)
    pour permettre sa rotation et sa révocation."""
    refresh_token, jti, expires_at = create_refresh_token(user_id)
    db.add_refresh_token(jti, user_id, expires_at)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=refresh_token,
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
    return _issue_tokens(db, user["id"])


@router.post("/v1/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: Database = Depends(get_db)) -> TokenResponse:
    user = db.get_user_by_email(req.email)
    if user is None or not verify_password(req.password, user["password_hash"]):
        raise ApiError("unauthenticated", "Identifiants invalides.", 401)
    return _issue_tokens(db, user["id"])


@router.post("/v1/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: Database = Depends(get_db)) -> TokenResponse:
    claims = decode_refresh(req.refresh_token)
    if claims is None:
        raise ApiError("unauthenticated", "refresh_token invalide ou expiré.", 401)
    user_id, jti = claims

    rec = db.get_refresh_token(jti)
    if rec is None or rec["user_id"] != user_id:
        # jti inconnu (jeton d'avant la rotation, ou forgé) → refuser.
        raise ApiError("unauthenticated", "refresh_token invalide ou expiré.", 401)
    if rec["revoked"]:
        # Réutilisation d'un refresh déjà tourné : vol probable. On coupe toute
        # la famille de jetons de l'utilisateur (reuse detection).
        db.revoke_all_refresh_tokens(user_id)
        raise ApiError("unauthenticated", "Session révoquée (jeton réutilisé).", 401)
    if db.get_user(user_id) is None:
        raise ApiError("unauthenticated", "refresh_token invalide ou expiré.", 401)

    # Rotation : l'ancien refresh est révoqué, un nouveau couple est émis.
    db.revoke_refresh_token(jti)
    return _issue_tokens(db, user_id)
