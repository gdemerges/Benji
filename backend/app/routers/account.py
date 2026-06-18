"""GET /v1/me — plan, droits, quotas (réel : usage depuis la DB)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import User, require_user
from app.db import Database, period_end_iso
from app.deps import get_db
from app.schemas import Entitlements, MeResponse, Quota

router = APIRouter()


@router.get("/v1/me", response_model=MeResponse)
async def me(
    user: User = Depends(require_user),
    db: Database = Depends(get_db),
) -> MeResponse:
    used = db.get_usage(user.user_id)
    return MeResponse(
        user_id=user.user_id,
        plan=user.plan,
        entitlements=Entitlements(
            cloud_stt=user.cloud_stt,
            cloud_summary=user.cloud_summary,
        ),
        quota=Quota(
            stt_seconds_used=int(used),
            stt_seconds_limit=user.stt_seconds_limit,
            period_end=period_end_iso(),
        ),
    )
