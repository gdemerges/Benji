import json

import pytest
from app.main import app
from app.routers import summary as summary_router
from fastapi.testclient import TestClient

client = TestClient(app)
AUTH = {"Authorization": "Bearer devtoken123"}

LONG_ENTRIES = [{"text": "Bonjour, ceci est une transcription suffisamment longue pour être résumée."}]


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_me_requires_auth():
    r = client.get("/v1/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthenticated"


def test_me_ok():
    r = client.get("/v1/me", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["entitlements"]["cloud_summary"] is True
    assert body["quota"]["stt_seconds_limit"] is None


def test_login_issues_tokens():
    r = client.post("/v1/auth/login", json={"email": "a@b.c", "password": "x"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "Bearer"
    assert r.json()["expires_in"] == 900


def test_summary_requires_auth():
    r = client.post("/v1/summary", json={"entries": LONG_ENTRIES})
    assert r.status_code == 401


def test_summary_rejects_short_transcription(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    r = client.post("/v1/summary", json={"entries": [{"text": "court"}]}, headers=AUTH)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_summary_missing_key_is_500(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/v1/summary", json={"entries": LONG_ENTRIES}, headers=AUTH)
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal"


def test_summary_streams_sse(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    async def fake_stream(text, model):
        assert model == "claude-haiku-4-5"  # alias "haiku" résolu
        yield "event: token\ndata: {\"text\": \"Voici \"}\n\n"
        yield "event: token\ndata: {\"text\": \"un résumé.\"}\n\n"
        yield "event: done\ndata: {\"summary_id\": \"sum_x\"}\n\n"

    monkeypatch.setattr(summary_router, "_stream_summary", fake_stream)

    with client.stream("POST", "/v1/summary",
                       json={"entries": LONG_ENTRIES, "model": "haiku"},
                       headers=AUTH) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())

    assert "event: token" in body
    assert "un résumé." in body
    assert "event: done" in body


def test_transcribe_handshake_and_metering():
    with client.websocket_connect("/v1/transcribe") as ws:
        ws.send_text(json.dumps({
            "type": "start",
            "token": "devtoken123",
            "audio": {"encoding": "pcm_s16le", "sample_rate": 16000, "channels": 1},
        }))
        assert ws.receive_json() == {"type": "ready"}

        # 32000 octets pcm_s16le @ 16 kHz mono = 1.0 s d'audio.
        ws.send_bytes(b"\x00" * 32000)
        ws.send_text(json.dumps({"type": "stop"}))

        closed = ws.receive_json()
        assert closed["type"] == "closed"
        assert closed["stt_seconds"] == pytest.approx(1.0)


def test_transcribe_rejects_unauthenticated():
    from starlette.websockets import WebSocketDisconnect

    with client.websocket_connect("/v1/transcribe") as ws:
        ws.send_text(json.dumps({"type": "start"}))  # pas de token
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4401
