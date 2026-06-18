"""Session STT factice, déterministe — pour les tests et le dev hors-ligne.

Aucun fournisseur externe : émet vad+segment_start au 1er chunk audio, un
`word` par mot scripté, puis `final_text` au `finish`.
"""

from __future__ import annotations

from app.stt.base import BaseSTTSession


class FakeSTTSession(BaseSTTSession):
    def __init__(self, words: list[str] | None = None, speaker: str | None = None):
        super().__init__()
        self._words = words if words is not None else ["bonjour", "le", "monde"]
        self._speaker = speaker
        self._started = False

    async def send_audio(self, chunk: bytes) -> None:
        if self._started:
            return
        self._started = True
        await self._emit({"type": "vad_status", "speaking": True})
        await self._emit({"type": "segment_start"})
        for w in self._words:
            await self._emit({"type": "word", "text": w})

    async def finish(self) -> None:
        text = " ".join(self._words).strip().capitalize()
        if text:
            msg: dict = {"type": "final_text", "text": text}
            if self._speaker:
                msg["speaker"] = self._speaker
            await self._emit(msg)
        await self._emit({"type": "vad_status", "speaking": False})
        await self._emit_done()
