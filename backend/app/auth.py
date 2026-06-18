"""Authentification (stub v1).

⚠️ Stub volontaire : tout jeton Bearer non vide est accepté et mappé sur un
utilisateur fictif. À remplacer par une vraie vérification JWT + plans. La forme
de la dépendance (`require_user`) ne changera pas quand on branchera le vrai
système.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header

from app.errors import ApiError


@dataclass
class User:
    user_id: str
    plan: str = "pro"
    cloud_stt: bool = True
    cloud_summary: bool = True


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


def require_user(authorization: str | None = Header(default=None)) -> User:
    """Dépendance FastAPI : exige un Bearer, renvoie l'utilisateur."""
    token = _extract_bearer(authorization)
    if token is None:
        raise ApiError("unauthenticated", "Jeton Bearer absent ou invalide.", 401)
    # Stub : on dérive un id du jeton ; le vrai backend décodera le JWT.
    return User(user_id=f"usr_{token[:8]}")


def user_from_token(token: str | None) -> User | None:
    """Variante hors-header pour le WebSocket (jeton dans le message `start`)."""
    if not token or not token.strip():
        return None
    return User(user_id=f"usr_{token.strip()[:8]}")
