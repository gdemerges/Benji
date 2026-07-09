"""Persistance SQLite (stdlib) : comptes utilisateurs + métering STT.

Volontairement minimal et sans ORM. Pour un vrai déploiement multi-instance,
remplacer par Postgres — l'interface `Database` est le seul point à réimplémenter.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def period_end_iso(period: str | None = None) -> str:
    period = period or current_period()
    year, month = (int(x) for x in period.split("-"))
    year2, month2 = (year + 1, 1) if month == 12 else (year, month + 1)
    return datetime(year2, month2, 1, tzinfo=UTC).isoformat()


class Database:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL + busy_timeout : lectures concurrentes non bloquées par une écriture,
        # et attente plutôt que "database is locked" sous contention. Reste
        # mono-instance ; le multi-instance impose un vrai serveur (Postgres).
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    stripe_customer_id TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage (
                    user_id TEXT NOT NULL,
                    period TEXT NOT NULL,
                    stt_seconds REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, period)
                );
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    jti TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens (user_id);
                """
            )
            self._conn.commit()

    # --- users ---

    def create_user(self, email: str, password_hash: str, plan: str = "free") -> dict:
        uid = f"usr_{uuid.uuid4().hex[:16]}"
        with self._lock:
            self._conn.execute(
                "INSERT INTO users (id, email, password_hash, plan, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid, email.lower(), password_hash, plan,
                 datetime.now(UTC).isoformat()),
            )
            self._conn.commit()
        return self.get_user(uid)

    def get_user(self, user_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.lower(),)
            ).fetchone()
        return dict(row) if row else None

    def set_plan(self, user_id: str, plan: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET plan = ? WHERE id = ?", (plan, user_id)
            )
            self._conn.commit()

    def set_plan_by_customer(self, stripe_customer_id: str, plan: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE users SET plan = ? WHERE stripe_customer_id = ?",
                (plan, stripe_customer_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def link_stripe_customer(self, user_id: str, customer_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
                (customer_id, user_id),
            )
            self._conn.commit()

    # --- refresh tokens (rotation + révocation) ---

    def add_refresh_token(self, jti: str, user_id: str, expires_at: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO refresh_tokens (jti, user_id, expires_at, created_at) "
                "VALUES (?, ?, ?, ?)",
                (jti, user_id, int(expires_at), datetime.now(UTC).isoformat()),
            )
            self._conn.commit()

    def get_refresh_token(self, jti: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM refresh_tokens WHERE jti = ?", (jti,)
            ).fetchone()
        return dict(row) if row else None

    def revoke_refresh_token(self, jti: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE refresh_tokens SET revoked = 1 WHERE jti = ?", (jti,)
            )
            self._conn.commit()

    def revoke_all_refresh_tokens(self, user_id: str) -> None:
        """Révoque toute la famille de refresh d'un utilisateur (détection de vol)."""
        with self._lock:
            self._conn.execute(
                "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?", (user_id,)
            )
            self._conn.commit()

    def purge_expired_refresh_tokens(self, now: int | None = None) -> None:
        now = int(now if now is not None else datetime.now(UTC).timestamp())
        with self._lock:
            self._conn.execute(
                "DELETE FROM refresh_tokens WHERE expires_at < ?", (now,)
            )
            self._conn.commit()

    # --- métering ---

    def add_usage(self, user_id: str, seconds: float, period: str | None = None) -> None:
        period = period or current_period()
        with self._lock:
            self._conn.execute(
                "INSERT INTO usage (user_id, period, stt_seconds) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, period) DO UPDATE SET "
                "stt_seconds = stt_seconds + excluded.stt_seconds",
                (user_id, period, float(seconds)),
            )
            self._conn.commit()

    def get_usage(self, user_id: str, period: str | None = None) -> float:
        period = period or current_period()
        with self._lock:
            row = self._conn.execute(
                "SELECT stt_seconds FROM usage WHERE user_id = ? AND period = ?",
                (user_id, period),
            ).fetchone()
        return float(row["stt_seconds"]) if row else 0.0
