"""RemoteSTTClient : conversion audio, handshake, relais d'events — sans réseau."""

import json
import threading
import time
from queue import Queue

import numpy as np

from benji.config import LLMConfig, STTConfig
from benji.stt.remote import (
    RemoteSTTClient,
    build_remote_stt_client,
    float32_to_pcm16,
)


class FakeConn:
    """Connexion WS factice : enregistre les envois, scripte les réceptions."""

    def __init__(self, recv_script):
        self.sent: list = []
        self._recv = list(recv_script)

    def send(self, data):
        self.sent.append(data)

    def recv(self):
        if not self._recv:
            raise ConnectionError("closed")
        return self._recv.pop(0)

    def close(self):
        pass


class FakeHistory:
    def __init__(self):
        self.added: list = []

    def add(self, text, speaker=None):
        self.added.append((text, speaker))


def _client(recv_script=None, history=None):
    conn = FakeConn(recv_script or [])
    client = RemoteSTTClient(
        Queue(), Queue(), history,
        ws_url="ws://test/v1/transcribe", token="tok",
        sample_rate=16000, language="fr", diarization=True, glossary=["MLX"],
        connect=lambda: conn,
    )
    return client, conn


def test_float32_to_pcm16_roundtrip():
    samples = np.array([0.0, 1.0, -1.0, 0.5], dtype=np.float32)
    raw = float32_to_pcm16(samples)
    back = np.frombuffer(raw, dtype="<i2")
    assert back.tolist() == [0, 32767, -32767, 16383]


def test_float32_to_pcm16_clips():
    raw = float32_to_pcm16(np.array([2.0, -2.0], dtype=np.float32))
    assert np.frombuffer(raw, dtype="<i2").tolist() == [32767, -32767]


def test_start_message_shape():
    client, _ = _client()
    msg = client.start_message()
    assert msg["type"] == "start"
    assert msg["token"] == "tok"
    assert msg["audio"] == {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1}
    assert msg["language"] == "fr"
    assert msg["diarization"] is True
    assert msg["glossary"] == ["MLX"]


def test_send_loop_streams_pcm_then_stop():
    client, conn = _client()
    chunk = np.array([0.5, -0.5], dtype=np.float32)
    client.audio_queue.put(chunk)
    client.audio_queue.put(None)  # sentinelle de fin

    client._send_loop(conn, threading.Event())

    assert conn.sent[0] == float32_to_pcm16(chunk)
    assert json.loads(conn.sent[1]) == {"type": "stop"}
    # La sentinelle marque l'arrêt définitif (pas de reconnexion ensuite).
    assert client._shutdown.is_set()


def test_send_loop_exits_on_conn_closed_without_stealing_chunks():
    # À la déconnexion, le sender du cycle précédent doit se terminer sans
    # consommer les chunks destinés à la connexion suivante.
    client, conn = _client()
    closed = threading.Event()
    closed.set()
    client.audio_queue.put(np.zeros(2, dtype=np.float32))

    client._send_loop(conn, closed)

    assert conn.sent == []
    assert client.audio_queue.qsize() == 1


def test_recv_loop_relays_events_and_persists_final():
    history = FakeHistory()
    script = [
        json.dumps({"type": "vad_status", "speaking": True}),
        json.dumps({"type": "segment_start"}),
        json.dumps({"type": "word", "text": "bonjour"}),
        json.dumps({"type": "final_text", "text": "Bonjour le monde", "speaker": "A"}),
        json.dumps({"type": "closed", "stt_seconds": 1.0}),
    ]
    client, conn = _client(recv_script=script, history=history)

    client._recv_loop(conn)

    relayed = []
    while not client.display_queue.empty():
        relayed.append(client.display_queue.get())
    assert [e["type"] for e in relayed] == [
        "vad_status", "segment_start", "word", "final_text",
    ]
    # final_text persisté avec le speaker ; "closed" stoppe la boucle.
    assert history.added == [("Bonjour le monde", "A")]


def test_recv_loop_ignores_dropped_final():
    history = FakeHistory()
    script = [
        json.dumps({"type": "final_text", "text": "", "drop": True}),
        json.dumps({"type": "closed"}),
    ]
    client, conn = _client(recv_script=script, history=history)
    client._recv_loop(conn)
    assert history.added == []  # un final droppé n'est pas persisté


def test_run_reconnects_after_connection_loss():
    """Perte de connexion → backoff, event UI « pas de parole », reconnexion."""
    display = Queue()
    attempts = {"n": 0}

    def connect():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ConnectionError("réseau tombé")  # 1er essai : échec
        # Ensuite : handshake ok, puis le backend ferme aussitôt.
        return FakeConn([json.dumps({"type": "ready"}), json.dumps({"type": "closed"})])

    client = RemoteSTTClient(
        Queue(), display, None, ws_url="ws://test/v1/transcribe", connect=connect,
    )
    client._backoff_initial = 0.01
    client._backoff_max = 0.02

    t = threading.Thread(target=client.run, daemon=True)
    t.start()
    # Attendre au moins un échec + deux connexions réussies (reconnexion prouvée).
    deadline = time.monotonic() + 5.0
    while attempts["n"] < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert attempts["n"] >= 3

    # La sentinelle None (shutdown) termine définitivement la boucle.
    client.audio_queue.put(None)
    t.join(timeout=5.0)
    assert not t.is_alive()

    # Chaque déconnexion a poussé un vad_status speaking=False vers l'UI.
    events = []
    while not display.empty():
        events.append(display.get())
    assert {"type": "vad_status", "speaking": False} in events


def test_token_provider_used_at_each_connection():
    tokens = iter(["tok-1", "tok-2"])
    client = RemoteSTTClient(
        Queue(), Queue(), None, ws_url="ws://test/v1/transcribe",
        token="statique", token_provider=lambda: next(tokens),
        connect=lambda: FakeConn([]),
    )
    # Le provider prime sur le token statique et est rappelé à chaque connexion.
    assert client.start_message()["token"] == "tok-1"
    assert client.start_message()["token"] == "tok-2"


def test_builder_converts_http_to_ws():
    client = build_remote_stt_client(
        Queue(), Queue(), None,
        STTConfig(stt_provider="remote"),
        LLMConfig(backend_url="https://api.benji.app", backend_token="t"),
    )
    assert client._ws_url == "wss://api.benji.app/v1/transcribe"
