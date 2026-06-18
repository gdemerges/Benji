"""Schémas de requête/réponse (cf. docs/api-contract.md)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# --- Auth (§1) ---

class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


# --- Compte (§2) ---

class Entitlements(BaseModel):
    cloud_stt: bool
    cloud_summary: bool


class Quota(BaseModel):
    stt_seconds_used: int
    stt_seconds_limit: int | None
    period_end: str | None = None


class MeResponse(BaseModel):
    user_id: str
    plan: str
    entitlements: Entitlements
    quota: Quota


# --- Résumé (§4) ---

class SummaryEntry(BaseModel):
    timestamp: str | None = None
    text: str
    speaker: str | None = None


class SummaryRequest(BaseModel):
    entries: list[SummaryEntry] = Field(default_factory=list)
    model: str = "haiku"  # alias logique ; le serveur résout l'ID Anthropic


# --- Historique (§5) ---

class HistoryItem(BaseModel):
    id: str
    timestamp: str
    text: str
    speaker: str | None = None


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    next_cursor: str | None = None
