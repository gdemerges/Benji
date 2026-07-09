"""Hachage de mot de passe (PBKDF2, stdlib) et jetons JWT (HS256)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
import uuid

import jwt

from app.config import (
    ACCESS_TTL_SECONDS,
    REFRESH_TTL_SECONDS,
    jwt_secret,
)

_PBKDF2_ITERS = 200_000


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERS)
    return f"pbkdf2_sha256${_PBKDF2_ITERS}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), _unb64(salt_b64), int(iters)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, _unb64(dk_b64))


def _make_token(sub: str, token_type: str, ttl: int, jti: str | None = None) -> str:
    now = int(time.time())
    payload = {"sub": sub, "type": token_type, "iat": now, "exp": now + ttl}
    if jti is not None:
        payload["jti"] = jti
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def create_access_token(sub: str) -> str:
    return _make_token(sub, "access", ACCESS_TTL_SECONDS)


def create_refresh_token(sub: str) -> tuple[str, str, int]:
    """Crée un refresh token porteur d'un `jti` unique.

    Renvoie `(token, jti, expires_at)` — le `jti` et l'expiration sont persistés
    côté serveur (table `refresh_tokens`) pour permettre la rotation et la
    révocation (un refresh stateless ne peut être ni tourné ni invalidé).
    """
    jti = uuid.uuid4().hex
    expires_at = int(time.time()) + REFRESH_TTL_SECONDS
    token = _make_token(sub, "refresh", REFRESH_TTL_SECONDS, jti=jti)
    return token, jti, expires_at


def decode_token(token: str, expected_type: str) -> str | None:
    """Retourne le `sub` si le jeton est valide et du bon type, sinon None."""
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload.get("sub")


def decode_refresh(token: str) -> tuple[str, str] | None:
    """Valide un refresh token et renvoie `(sub, jti)`, sinon None.

    Un jeton sans `jti` (émis avant la rotation) est refusé : il ne peut plus
    être suivi côté serveur, donc on force une reconnexion.
    """
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "refresh":
        return None
    sub, jti = payload.get("sub"), payload.get("jti")
    if not sub or not jti:
        return None
    return sub, jti
