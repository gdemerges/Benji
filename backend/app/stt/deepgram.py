"""Session STT Deepgram (streaming temps réel).

Traduit le flux Deepgram vers les events du contrat Benji. Le branchement réel
nécessite DEEPGRAM_API_KEY et une validation en conditions réelles (non couvert
par les tests hermétiques, qui utilisent FakeSTTSession).

Mapping :
  SpeechStarted  → vad_status(speaking=true) + segment_start
  UtteranceEnd   → vad_status(speaking=false)
  Results interim→ `word` (deltas par rapport au partiel précédent)
  Results final  → final_text (+ speaker si diarisation)
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlencode

from app.stt.base import BaseSTTSession

log = logging.getLogger(__name__)

_DG_URL = "wss://api.deepgram.com/v1/listen"


def _speaker_label(n) -> str | None:
    if n is None:
        return None
    n = int(n)
    return chr(ord("A") + n) if 0 <= n < 26 else f"S{n}"


class DeepgramSTTSession(BaseSTTSession):
    def __init__(
        self,
        api_key: str,
        sample_rate: int = 16000,
        language: str = "fr",
        diarization: bool = True,
        model: str = "nova-3",
    ):
        super().__init__()
        self._api_key = api_key
        self._params = {
            "encoding": "linear16",
            "sample_rate": str(sample_rate),
            "channels": "1",
            "language": language,
            "model": model,
            "interim_results": "true",
            "punctuate": "true",
            "vad_events": "true",
            "diarize": "true" if diarization else "false",
        }
        self._ws = None
        self._reader: asyncio.Task | None = None
        self._partial_words: list[str] = []

    async def open(self) -> None:
        import websockets

        url = f"{_DG_URL}?{urlencode(self._params)}"
        self._ws = await websockets.connect(
            url, additional_headers={"Authorization": f"Token {self._api_key}"}
        )
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await self._translate(msg)
        except Exception as e:  # fermeture / réseau
            log.warning("Deepgram read loop ended: %s", e)
        finally:
            await self._emit_done()

    async def _translate(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == "SpeechStarted":
            await self._emit({"type": "vad_status", "speaking": True})
            await self._emit({"type": "segment_start"})
            self._partial_words = []
            return
        if mtype == "UtteranceEnd":
            await self._emit({"type": "vad_status", "speaking": False})
            return
        if mtype != "Results":
            return

        alt = (msg.get("channel", {}).get("alternatives") or [{}])[0]
        transcript = (alt.get("transcript") or "").strip()
        if not transcript:
            return

        if not msg.get("is_final"):
            words = transcript.split()
            for w in words[len(self._partial_words):]:
                await self._emit({"type": "word", "text": w})
            self._partial_words = words
            return

        # Segment finalisé.
        out: dict = {"type": "final_text", "text": transcript}
        dg_words = alt.get("words") or []
        if dg_words and "speaker" in dg_words[0]:
            spk = _speaker_label(dg_words[0].get("speaker"))
            if spk:
                out["speaker"] = spk
        await self._emit(out)
        self._partial_words = []

    async def send_audio(self, chunk: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(chunk)

    async def finish(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass
        # _read_loop émettra _emit_done à la fermeture du flux Deepgram.

    async def close(self) -> None:
        if self._reader is not None:
            self._reader.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        await self._emit_done()
