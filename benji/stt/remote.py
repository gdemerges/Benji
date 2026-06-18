"""Client STT distant : streame le micro vers le backend Benji et relaie les
events de transcription vers `display_queue` (cf. docs/api-contract.md §3).

Bypasse VAD + Whisper local : en mode `STTConfig.stt_provider = "remote"`, le
backend fait la transcription (Deepgram). Le client ne fait que convertir
l'audio en PCM 16-bit et router les events du contrat — qui parlent déjà le
vocabulaire de `display_queue` (`vad_status`/`segment_start`/`word`/`final_text`).
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
from queue import Queue

import numpy as np

log = logging.getLogger(__name__)

# Events de transcription relayés tels quels vers l'UI.
_RELAYED = {"vad_status", "segment_start", "word", "final_text"}


def _http_to_ws(url: str) -> str:
    if url.startswith("https://"):
        return "wss://" + url[len("https://"):]
    if url.startswith("http://"):
        return "ws://" + url[len("http://"):]
    return url


def float32_to_pcm16(chunk) -> bytes:
    """np.float32 [-1, 1] → PCM 16-bit signé little-endian (linear16)."""
    arr = np.asarray(chunk, dtype=np.float32)
    clipped = np.clip(arr, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


class RemoteSTTClient:
    def __init__(
        self,
        audio_queue: Queue,
        display_queue: Queue,
        history,
        *,
        ws_url: str,
        token: str | None = None,
        sample_rate: int = 16000,
        language: str | None = "fr",
        diarization: bool = True,
        glossary: list[str] | None = None,
        connect=None,  # () -> connexion WS (injectable pour tests)
    ):
        self.audio_queue = audio_queue
        self.display_queue = display_queue
        self.history = history
        self._ws_url = ws_url
        self._token = token
        self._sample_rate = sample_rate
        self._language = language
        self._diarization = diarization
        self._glossary = glossary or []
        self._connect = connect or self._default_connect
        self._stop = threading.Event()

    # --- transport réel ---

    def _default_connect(self):
        from websockets.sync.client import connect
        return connect(self._ws_url)

    def start_message(self) -> dict:
        return {
            "type": "start",
            "token": self._token,
            "audio": {
                "encoding": "pcm_s16le",
                "sample_rate": self._sample_rate,
                "channels": 1,
            },
            "language": self._language,
            "diarization": self._diarization,
            "glossary": self._glossary,
        }

    # --- boucles ---

    def _send_loop(self, conn) -> None:
        """Pousse les frames audio (audio_queue → backend). None = fin."""
        while not self._stop.is_set():
            chunk = self.audio_queue.get()
            if chunk is None:
                with contextlib.suppress(Exception):
                    conn.send(json.dumps({"type": "stop"}))
                return
            with contextlib.suppress(Exception):
                conn.send(float32_to_pcm16(chunk))

    def _recv_loop(self, conn) -> None:
        """Relaie les events backend → display_queue (+ historique)."""
        while True:
            try:
                raw = conn.recv()
            except Exception:  # connexion fermée
                return
            if raw is None:
                return
            try:
                ev = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            etype = ev.get("type")
            if etype in ("closed", "error"):
                if etype == "error":
                    log.warning("Backend STT error: %s", ev.get("message"))
                return
            if etype in _RELAYED:
                self.display_queue.put(ev)
                if (
                    etype == "final_text"
                    and not ev.get("drop")
                    and ev.get("text")
                    and self.history is not None
                ):
                    self.history.add(ev["text"], speaker=ev.get("speaker"))

    def run(self) -> None:
        """Boucle bloquante (à lancer dans un thread)."""
        try:
            conn = self._connect()
        except Exception as e:
            log.error("Connexion STT distante impossible: %s", e)
            return
        try:
            conn.send(json.dumps(self.start_message()))
            ready = json.loads(conn.recv())
            if ready.get("type") != "ready":
                log.error("Handshake STT distant inattendu: %s", ready)
                return
            sender = threading.Thread(
                target=self._send_loop, args=(conn,), daemon=True, name="RemoteSTT-send"
            )
            sender.start()
            self._recv_loop(conn)  # bloque jusqu'à closed/erreur
            self._stop.set()
        finally:
            with contextlib.suppress(Exception):
                conn.close()

    def stop(self) -> None:
        self._stop.set()


def build_remote_stt_client(
    audio_queue: Queue,
    display_queue: Queue,
    history,
    stt_cfg,
    llm_cfg,
    sample_rate: int = 16000,
) -> RemoteSTTClient:
    """Construit le client STT distant depuis les configs (backend = LLMConfig)."""
    ws_url = _http_to_ws(llm_cfg.backend_url).rstrip("/") + "/v1/transcribe"
    return RemoteSTTClient(
        audio_queue,
        display_queue,
        history,
        ws_url=ws_url,
        token=llm_cfg.backend_token,
        sample_rate=sample_rate,
        language=stt_cfg.language,
        diarization=stt_cfg.diarization,
        glossary=stt_cfg.glossary,
    )
