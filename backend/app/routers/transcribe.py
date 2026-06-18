"""WebSocket /v1/transcribe — transcription temps réel (cf. api-contract §3).

État : **squelette conforme au contrat**. Le handshake, l'auth, la réception des
frames audio binaires et le métering des secondes sont en place. Le branchement
d'un vrai provider STT (Deepgram, etc.) qui émet `segment_start`/`word`/
`final_text`/`vad_status` est l'étape suivante (TODO ci-dessous).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.auth import user_from_token

log = logging.getLogger(__name__)
router = APIRouter()

# Codes de fermeture WS (cf. api-contract §6).
WS_UNAUTHENTICATED = 4401
WS_FORBIDDEN = 4403

_BYTES_PER_SAMPLE = 2  # pcm_s16le


async def _send(ws: WebSocket, payload: dict) -> None:
    await ws.send_text(json.dumps(payload, ensure_ascii=False))


@router.websocket("/v1/transcribe")
async def transcribe(ws: WebSocket) -> None:
    await ws.accept()

    # 1) Premier message : `start` (auth + config audio).
    try:
        raw = await ws.receive_text()
        start = json.loads(raw)
    except (WebSocketDisconnect, json.JSONDecodeError, KeyError):
        await ws.close(code=WS_UNAUTHENTICATED)
        return

    if start.get("type") != "start":
        await ws.close(code=WS_UNAUTHENTICATED)
        return

    user = user_from_token(start.get("token"))
    if user is None:
        await ws.close(code=WS_UNAUTHENTICATED)
        return
    if not user.cloud_stt:
        await ws.close(code=WS_FORBIDDEN)
        return

    audio = start.get("audio") or {}
    sample_rate = int(audio.get("sample_rate", 16000)) or 16000

    await _send(ws, {"type": "ready"})

    # 2) Boucle : frames audio binaires + contrôle JSON.
    total_bytes = 0
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if (data := msg.get("bytes")) is not None:
                total_bytes += len(data)
                # TODO(stt): pousser `data` dans le provider STT et relayer ses
                # events (segment_start / word / final_text / vad_status).
                continue
            if (text := msg.get("text")) is not None:
                try:
                    ctrl = json.loads(text)
                except json.JSONDecodeError:
                    continue
                if ctrl.get("type") == "stop":
                    break
    except WebSocketDisconnect:
        return

    # 3) Clôture : conso facturable (secondes d'audio reçues).
    stt_seconds = round(total_bytes / (sample_rate * _BYTES_PER_SAMPLE), 1)
    try:
        await _send(ws, {"type": "closed", "stt_seconds": stt_seconds})
        await ws.close()
    except RuntimeError:
        pass  # déjà fermé côté client
