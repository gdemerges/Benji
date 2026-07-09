"""Rate limiting en mémoire (fenêtre glissante) pour les endpoints sensibles.

Suffisant pour un backend mono-instance (SQLite) : borne le brute-force sur
`/v1/auth/login` et l'énumération de comptes. En multi-instance, remplacer le
stockage en mémoire par un store partagé (Redis) — l'interface `RateLimiter`
reste la même.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.errors import ApiError


class RateLimiter:
    """Fenêtre glissante par clé : au plus `max_hits` tentatives par `window` s."""

    def __init__(self, max_hits: int, window_seconds: float):
        self.max_hits = max_hits
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Enregistre une tentative ; True si sous la limite, False si dépassée."""
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_hits:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Limiteur des endpoints d'auth : 10 tentatives / 60 s par IP (surchargeable).
_login_limiter = RateLimiter(
    max_hits=_env_int("AUTH_RATE_LIMIT_MAX", 10),
    window_seconds=_env_int("AUTH_RATE_LIMIT_WINDOW", 60),
)

_all_limiters = [_login_limiter]


def reset_all_limiters() -> None:
    """Vide l'état de tous les limiteurs (utilisé par les tests pour l'isolation)."""
    for lim in _all_limiters:
        lim.reset()


def _client_key(request: Request) -> str:
    # request.client.host = IP directe. Derrière un reverse proxy de confiance,
    # préférer X-Forwarded-For (non fait ici : à activer une fois le proxy connu).
    client = request.client
    return client.host if client else "unknown"


def rate_limit_auth(request: Request) -> None:
    """Dépendance FastAPI : borne les tentatives sur les endpoints d'auth."""
    if not _login_limiter.hit(_client_key(request)):
        raise ApiError("rate_limited", "Trop de tentatives. Réessaie plus tard.", 429)
