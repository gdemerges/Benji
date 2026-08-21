"""Registre des réunions : la transcription est découpée en unités nommées.

Jusqu'ici l'historique était un flux plat : fermer puis rouvrir Benji mélangeait
deux réunions dans le même fichier, et « résumer la session » ne pouvait
s'accrocher qu'à l'heure de démarrage du process. Une réunion est désormais une
entité de premier ordre — elle a un identifiant, un titre modifiable, un début et
une fin — et chaque entrée d'historique porte l'identifiant de la sienne.

Module pur (ni Qt ni audio) : testable sans lancer l'app. Le fichier
`meetings.json` est écrit en 0600 dès la création, comme le reste des données de
réunion, et de façon atomique (tmp + `os.replace`) pour qu'un crash au milieu
d'une écriture ne laisse jamais un registre tronqué.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime

from benji.paths import user_path

log = logging.getLogger(__name__)

# Identifiant réservé aux entrées écrites avant l'existence des réunions : elles
# n'ont pas de `meeting`, on les regroupe sous une réunion virtuelle.
LEGACY_ID = "legacy"
LEGACY_TITLE = "Sessions précédentes"

_STORE_NAME = "meetings.json"


def default_title(started_at: datetime) -> str:
    return f"Réunion du {started_at.strftime('%d/%m à %H:%M')}"


@dataclass
class Meeting:
    id: str
    title: str
    started_at: datetime
    ended_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Meeting | None:
        try:
            ended = raw.get("ended_at")
            return cls(
                id=str(raw["id"]),
                title=str(raw.get("title") or ""),
                started_at=datetime.fromisoformat(raw["started_at"]),
                ended_at=datetime.fromisoformat(ended) if ended else None,
            )
        except (KeyError, TypeError, ValueError):
            # Ligne corrompue : on l'ignore plutôt que de perdre tout le registre.
            return None


class MeetingStore:
    """Liste persistée des réunions, la plus récente en premier."""

    def __init__(self, path=None):
        self.path = path or user_path(_STORE_NAME)
        self._lock = threading.Lock()

    # --- lecture ---

    def list(self) -> list[Meeting]:
        raw = self._read()
        meetings = [m for m in (Meeting.from_dict(r) for r in raw) if m is not None]
        meetings.sort(key=lambda m: m.started_at, reverse=True)
        return meetings

    def get(self, meeting_id: str) -> Meeting | None:
        for meeting in self.list():
            if meeting.id == meeting_id:
                return meeting
        return None

    # --- écriture ---

    def start(self, title: str | None = None, *, now: datetime | None = None) -> Meeting:
        """Clôt la réunion ouverte (s'il y en a une) et en ouvre une nouvelle."""
        started = now or datetime.now()
        meeting = Meeting(
            id=uuid.uuid4().hex,
            title=(title or "").strip() or default_title(started),
            started_at=started,
        )
        with self._lock:
            raw = self._read()
            for entry in raw:
                if entry.get("ended_at") is None:
                    entry["ended_at"] = started.isoformat()
            raw.append(meeting.to_dict())
            self._write(raw)
        return meeting

    def end(self, meeting_id: str, *, now: datetime | None = None) -> None:
        stamp = (now or datetime.now()).isoformat()
        with self._lock:
            raw = self._read()
            for entry in raw:
                if entry.get("id") == meeting_id and entry.get("ended_at") is None:
                    entry["ended_at"] = stamp
            self._write(raw)

    def rename(self, meeting_id: str, title: str) -> None:
        title = title.strip()
        if not title:
            return
        with self._lock:
            raw = self._read()
            for entry in raw:
                if entry.get("id") == meeting_id:
                    entry["title"] = title
            self._write(raw)

    def delete(self, meeting_id: str) -> None:
        with self._lock:
            raw = [e for e in self._read() if e.get("id") != meeting_id]
            self._write(raw)

    # --- I/O ---

    def _read(self) -> list[dict]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Registre des réunions illisible (%s) — repart à vide", e)
            return []
        return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []

    def _write(self, raw: list[dict]) -> None:
        tmp = self.path.with_suffix(".json.tmp")
        # 0600 dès l'`os.open` : un write-puis-chmod laisserait les titres de
        # réunion lisibles par tous entre les deux appels.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


# --- réunion courante (process-wide) ---
#
# `TranscriptionHistory` est instancié à plusieurs endroits (transcriber, résumé
# live, fenêtre d'historique) et tous écrivent le même fichier : la réunion
# courante doit être un état partagé du process, pas de l'instance.

_current_lock = threading.Lock()
_current: Meeting | None = None
_store: MeetingStore | None = None


def _store_locked() -> MeetingStore:
    """Store partagé. À n'appeler qu'avec `_current_lock` tenu."""
    global _store
    if _store is None:
        _store = MeetingStore()
    return _store


def store() -> MeetingStore:
    with _current_lock:
        return _store_locked()


def current_meeting() -> Meeting:
    """Réunion en cours, ouverte paresseusement au premier besoin."""
    global _current
    with _current_lock:
        if _current is None:
            _current = _store_locked().start()
        return _current


def current_meeting_id() -> str | None:
    """Identifiant de la réunion en cours, *sans* en ouvrir une.

    Les chemins de lecture (activer un bouton, filtrer un résumé) ne doivent pas
    créer une réunion vide par simple curiosité : seule une transcription écrite
    ouvre une réunion.
    """
    with _current_lock:
        return _current.id if _current is not None else None


def start_meeting(title: str | None = None) -> Meeting:
    """Clôt la réunion courante et en démarre une nouvelle."""
    global _current
    with _current_lock:
        s = _store_locked()
        if _current is not None:
            s.end(_current.id)
        _current = s.start(title)
        return _current


def end_current_meeting() -> None:
    """Horodate la fin de la réunion courante (appelé à l'arrêt de l'app)."""
    global _current
    with _current_lock:
        if _current is not None:
            _store_locked().end(_current.id)
            _current = None


def reset_for_tests() -> None:
    """Remet à zéro l'état de module (les tests isolent HOME par tmp_path)."""
    global _current, _store
    with _current_lock:
        _current = None
        _store = None
