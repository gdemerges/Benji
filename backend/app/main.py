"""Point d'entrée FastAPI du backend Benji.

Lancer en dev : `uvicorn app.main:app --reload` (depuis backend/).
Voir docs/api-contract.md pour le contrat exposé.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI

from app.errors import ApiError, api_error_handler
from app.monitoring import init_sentry
from app.routers import account, auth, billing, history, summary, transcribe

logging.basicConfig(level=logging.INFO)
init_sentry()  # no-op sans SENTRY_DSN

app = FastAPI(title="Benji backend", version="0.1.0")
app.add_exception_handler(ApiError, api_error_handler)

app.include_router(auth.router, tags=["auth"])
app.include_router(account.router, tags=["account"])
app.include_router(summary.router, tags=["summary"])
app.include_router(history.router, tags=["history"])
app.include_router(billing.router, tags=["billing"])
app.include_router(transcribe.router, tags=["transcribe"])


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}
