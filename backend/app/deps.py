"""Dépendances FastAPI partagées (base de données)."""

from __future__ import annotations

import functools

from app.config import db_path
from app.db import Database


@functools.lru_cache(maxsize=1)
def _default_db() -> Database:
    return Database(db_path())


def get_db() -> Database:
    """Dépendance injectable (override possible en test)."""
    return _default_db()
