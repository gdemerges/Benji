"""Authentification : vérification du jeton d'accès JWT + droits du plan."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header

from app.db import Database
from app.deps import get_db
from app.errors import ApiError
from app.plans import Plan, get_plan
from app.security import decode_token


@dataclass
class User:
    user_id: str
    plan: str

    @property
    def _plan(self) -> Plan:
        return get_plan(self.plan)

    @property
    def cloud_stt(self) -> bool:
        return self._plan.cloud_stt

    @property
    def cloud_summary(self) -> bool:
        return self._plan.cloud_summary

    @property
    def stt_seconds_limit(self) -> int | None:
        return self._plan.stt_seconds_limit


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def authenticate(token: str | None, db: Database) -> User | None:
    """Décode un jeton d'accès et charge l'utilisateur (plan à jour)."""
    if not token:
        return None
    user_id = decode_token(token, "access")
    if user_id is None:
        return None
    row = db.get_user(user_id)
    if row is None:
        return None
    return User(user_id=row["id"], plan=row["plan"])


def require_user(
    authorization: str | None = Header(default=None),
    db: Database = Depends(get_db),
) -> User:
    user = authenticate(_bearer(authorization), db)
    if user is None:
        raise ApiError("unauthenticated", "Jeton invalide ou expiré.", 401)
    return user
