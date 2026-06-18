"""GET /v1/me — plan, droits, quotas (stub v1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import User, require_user
from app.schemas import Entitlements, MeResponse, Quota

router = APIRouter()


@router.get("/v1/me", response_model=MeResponse)
async def me(user: User = Depends(require_user)) -> MeResponse:
    # Stub : quotas figés. Le vrai backend lira l'état d'abonnement + le métering.
    return MeResponse(
        user_id=user.user_id,
        plan=user.plan,
        entitlements=Entitlements(
            cloud_stt=user.cloud_stt,
            cloud_summary=user.cloud_summary,
        ),
        quota=Quota(stt_seconds_used=0, stt_seconds_limit=None),
    )
