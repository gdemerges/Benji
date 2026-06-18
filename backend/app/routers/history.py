"""GET /v1/history — historique paginé (stub v1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import User, require_user
from app.schemas import HistoryResponse

router = APIRouter()


@router.get("/v1/history", response_model=HistoryResponse)
async def history(
    limit: int = 50,
    before: str | None = None,
    user: User = Depends(require_user),
) -> HistoryResponse:
    # Stub : pas encore de persistance serveur. Le client desktop gère son
    # historique en local en mode 100 % local.
    return HistoryResponse(items=[], next_cursor=None)
