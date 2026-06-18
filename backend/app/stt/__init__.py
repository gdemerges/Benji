"""Provider STT temps réel : fabrique de session selon la config serveur.

`STT_BACKEND` (env) : "deepgram" (défaut) ou "fake" (tests/dev hors-ligne).
Deepgram exige `DEEPGRAM_API_KEY`.
"""

from __future__ import annotations

import os

from app.stt.base import BaseSTTSession, STTSession
from app.stt.deepgram import DeepgramSTTSession
from app.stt.fake import FakeSTTSession

__all__ = [
    "STTSession",
    "BaseSTTSession",
    "DeepgramSTTSession",
    "FakeSTTSession",
    "make_session",
]


def make_session(start: dict) -> STTSession:
    """Construit une session STT depuis le message `start` du client."""
    audio = start.get("audio") or {}
    sample_rate = int(audio.get("sample_rate", 16000)) or 16000
    language = start.get("language", "fr")
    diarization = bool(start.get("diarization", True))

    backend = os.environ.get("STT_BACKEND", "deepgram").lower()
    if backend == "fake":
        return FakeSTTSession()

    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        raise RuntimeError("DEEPGRAM_API_KEY non configurée côté backend.")
    return DeepgramSTTSession(
        key, sample_rate=sample_rate, language=language, diarization=diarization
    )
