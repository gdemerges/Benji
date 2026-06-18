"""/v1/auth/* — délivrance de jetons (stub v1).

⚠️ Stub : accepte n'importe quel couple email/mot de passe et renvoie des jetons
factices. À remplacer par une vraie vérification d'identité + signature JWT.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.errors import ApiError
from app.schemas import LoginRequest, RefreshRequest, TokenResponse

router = APIRouter()

_ACCESS_TTL = 900  # 15 min


def _issue(subject: str) -> TokenResponse:
    return TokenResponse(
        access_token=f"dev.{subject}.{uuid.uuid4().hex}",
        refresh_token=f"refresh.{uuid.uuid4().hex}",
        expires_in=_ACCESS_TTL,
    )


@router.post("/v1/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest) -> TokenResponse:
    if not req.email or not req.password:
        raise ApiError("bad_request", "email et password requis.", 400)
    return _issue(req.email)


@router.post("/v1/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest) -> TokenResponse:
    if not req.refresh_token:
        raise ApiError("unauthenticated", "refresh_token requis.", 401)
    return _issue("refreshed")
