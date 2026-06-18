"""RemoteSTTClient : conversion audio, handshake, relais d'events — sans réseau."""

import json
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

    client._send_loop(conn)

    assert conn.sent[0] == float32_to_pcm16(chunk)
    assert json.loads(conn.sent[1]) == {"type": "stop"}


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


def test_builder_converts_http_to_ws():
    client = build_remote_stt_client(
        Queue(), Queue(), None,
        STTConfig(stt_provider="remote"),
        LLMConfig(backend_url="https://api.benji.app", backend_token="t"),
    )
    assert client._ws_url == "wss://api.benji.app/v1/transcribe"
