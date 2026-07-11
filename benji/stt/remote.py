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
from collections.abc import Callable
from queue import Empty, Full, Queue

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
        token_provider: Callable[[], str | None] | None = None,
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
        # Appelé à chaque (re)connexion : l'access token expire (~15 min), un
        # token figé au démarrage serait rejeté après reconnexion.
        self._token_provider = token_provider
        self._sample_rate = sample_rate
        self._language = language
        self._diarization = diarization
        self._glossary = glossary or []
        self._connect = connect or self._default_connect
        self._stop = threading.Event()
        # Set quand la sentinelle None (shutdown) a été consommée dans audio_queue.
        self._shutdown = threading.Event()
        # Backoff de reconnexion (1 s → 30 s, reset après connexion réussie).
        self._backoff_initial = 1.0
        self._backoff_max = 30.0

    # --- transport réel ---

    def _default_connect(self):
        from websockets.sync.client import connect
        return connect(self._ws_url)

    def start_message(self) -> dict:
        # Le provider prime sur le token statique : rafraîchi à chaque connexion.
        token = self._token_provider() if self._token_provider is not None else None
        return {
            "type": "start",
            "token": token if token is not None else self._token,
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

    def _send_loop(self, conn, conn_closed: threading.Event) -> None:
        """Pousse les frames audio (audio_queue → backend). None = fin définitive.

        `conn_closed` est propre à CHAQUE connexion : quand run() le set (après
        la fin du recv), le sender du cycle courant se termine sans voler de
        chunks à la connexion suivante — et sans rester bloqué sur get().
        """
        while not self._stop.is_set() and not conn_closed.is_set():
            try:
                chunk = self.audio_queue.get(timeout=0.2)
            except Empty:
                continue
            if chunk is None:
                self._shutdown.set()
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

    def _drain_stale_audio(self) -> bool:
        """Vide les chunks accumulés pendant la déconnexion (audio périmé,
        inutile de le rejouer). Retourne True si la sentinelle None (shutdown)
        a été rencontrée — le client doit alors s'arrêter définitivement."""
        while True:
            try:
                chunk = self.audio_queue.get_nowait()
            except Empty:
                return False
            if chunk is None:
                self._shutdown.set()
                return True

    def _notify_disconnected(self) -> None:
        """Éteint l'indicateur de parole côté UI (connexion perdue)."""
        with contextlib.suppress(Full):
            self.display_queue.put_nowait({"type": "vad_status", "speaking": False})

    def _run_one_connection(self) -> bool:
        """Un cycle connexion → handshake → stream. True si la connexion a
        été établie avec succès (handshake ok), False sinon."""
        conn = self._connect()
        try:
            conn.send(json.dumps(self.start_message()))
            ready = json.loads(conn.recv())
            if ready.get("type") != "ready":
                log.error("Handshake STT distant inattendu: %s", ready)
                return False
            # Event PAR connexion : signale au sender la fin de ce cycle.
            conn_closed = threading.Event()
            sender = threading.Thread(
                target=self._send_loop, args=(conn, conn_closed),
                daemon=True, name="RemoteSTT-send",
            )
            sender.start()
            try:
                self._recv_loop(conn)  # bloque jusqu'à closed/erreur
            finally:
                conn_closed.set()
                sender.join(timeout=2.0)
            return True
        finally:
            with contextlib.suppress(Exception):
                conn.close()

    def run(self) -> None:
        """Boucle bloquante (à lancer dans un thread) : reconnexion automatique
        avec backoff exponentiel tant que ni stop() ni la sentinelle None de
        shutdown n'ont été vus."""
        delay = self._backoff_initial
        while not self._stop.is_set() and not self._shutdown.is_set():
            connected = False
            try:
                connected = self._run_one_connection()
            except Exception as e:
                log.warning("Connexion STT distante en échec: %s", e)
            if connected:
                delay = self._backoff_initial  # reset après connexion réussie
            if self._stop.is_set() or self._shutdown.is_set():
                return
            # Connexion perdue : prévenir l'UI, purger l'audio périmé, retenter.
            log.warning("STT distant déconnecté — reconnexion dans %.0f s", delay)
            self._notify_disconnected()
            if self._drain_stale_audio():
                return  # sentinelle de shutdown reçue pendant la déconnexion
            if self._stop.wait(timeout=delay):
                return
            if self._drain_stale_audio():
                return
            delay = min(delay * 2, self._backoff_max)

    def stop(self) -> None:
        self._stop.set()


def build_remote_stt_client(
    audio_queue: Queue,
    display_queue: Queue,
    history,
    stt_cfg,
    llm_cfg,
    sample_rate: int = 16000,
    token_provider: Callable[[], str | None] | None = None,
) -> RemoteSTTClient:
    """Construit le client STT distant depuis les configs (backend = LLMConfig)."""
    ws_url = _http_to_ws(llm_cfg.backend_url).rstrip("/") + "/v1/transcribe"
    return RemoteSTTClient(
        audio_queue,
        display_queue,
        history,
        ws_url=ws_url,
        token=llm_cfg.backend_token,
        token_provider=token_provider,
        sample_rate=sample_rate,
        language=stt_cfg.language,
        diarization=stt_cfg.diarization,
        glossary=stt_cfg.glossary,
    )
