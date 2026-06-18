"""WebSocket /v1/transcribe — transcription temps réel (cf. api-contract §3).

Handshake `start`/`ready` + auth, puis deux flux concurrents :
- *feeder* : frames audio binaires du client → session STT (et métering)
- *forwarder* : events de la session (vad/segment_start/word/final_text) → client

Le provider STT concret est choisi par `app.stt.make_session` (Deepgram en prod,
Fake en test).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import authenticate
from app.deps import get_db
from app.stt import make_session

log = logging.getLogger(__name__)
router = APIRouter()

# Codes de fermeture WS (cf. api-contract §6).
WS_UNAUTHENTICATED = 4401
WS_FORBIDDEN = 4403
WS_QUOTA = 4429

_BYTES_PER_SAMPLE = 2  # pcm_s16le


async def _send(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload, ensure_ascii=False))


async def _forward(session, ws: WebSocket) -> None:
    async for event in session.events():
        await _send(ws, event)


@router.websocket("/v1/transcribe")
async def transcribe(ws: WebSocket) -> None:
    await ws.accept()

    # 1) Premier message : `start` (auth + config audio).
    try:
        start = json.loads(await ws.receive_text())
    except (WebSocketDisconnect, json.JSONDecodeError):
        await ws.close(code=WS_UNAUTHENTICATED)
        return
    if start.get("type") != "start":
        await ws.close(code=WS_UNAUTHENTICATED)
        return

    db = get_db()
    user = authenticate(start.get("token"), db)
    if user is None:
        await ws.close(code=WS_UNAUTHENTICATED)
        return
    if not user.cloud_stt:
        await ws.close(code=WS_FORBIDDEN)
        return

    # Quota STT (le poste facturable) : refus si le plafond du plan est atteint.
    limit = user.stt_seconds_limit
    if limit is not None and db.get_usage(user.user_id) >= limit:
        await _send(ws, {"type": "error", "code": "quota_exceeded",
                         "message": "Quota STT atteint."})
        await ws.close(code=WS_QUOTA)
        return

    audio = start.get("audio") or {}
    sample_rate = int(audio.get("sample_rate", 16000)) or 16000

    # 2) Ouverture de la session STT.
    try:
        session = make_session(start)
        await session.open()
    except Exception as e:
        log.warning("STT session open failed: %s", e)
        await _send(ws, {"type": "error", "code": "upstream_error", "message": str(e)})
        await ws.close()
        return

    await _send(ws, {"type": "ready"})
    forwarder = asyncio.create_task(_forward(session, ws))

    # 3) Feeder : frames audio + contrôle.
    total_bytes = 0
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if (data := msg.get("bytes")) is not None:
                total_bytes += len(data)
                await session.send_audio(data)
                continue
            if (text := msg.get("text")) is not None:
                try:
                    ctrl = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if ctrl.get("type") == "stop":
                    await session.finish()
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(forwarder, timeout=5)
        if not forwarder.done():
            forwarder.cancel()

    # 4) Clôture : conso facturable (secondes d'audio reçues) → métering.
    stt_seconds = round(total_bytes / (sample_rate * _BYTES_PER_SAMPLE), 1)
    if stt_seconds > 0:
        with contextlib.suppress(Exception):
            db.add_usage(user.user_id, stt_seconds)
    with contextlib.suppress(RuntimeError):
        await _send(ws, {"type": "closed", "stt_seconds": stt_seconds})
        await ws.close()
