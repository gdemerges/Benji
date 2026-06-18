"""POST /v1/summary — résumé via Claude, streamé en SSE (cf. api-contract §4).

Équivalent réseau du CloudSummaryProvider de l'app : le client envoie les
utterances + un alias logique de modèle ; le backend résout l'ID Anthropic,
streame les tokens et ne révèle jamais la clé.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app import prompts
from app.auth import User, require_user
from app.config import SUMMARY_MAX_TOKENS, anthropic_api_key, resolve_model
from app.errors import ApiError
from app.schemas import SummaryRequest

log = logging.getLogger(__name__)
router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_summary(text: str, model: str) -> AsyncIterator[str]:
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        yield _sse("error", {"code": "internal", "message": "anthropic non installé."})
        return

    client = AsyncAnthropic()  # lit ANTHROPIC_API_KEY
    try:
        async with client.messages.stream(
            model=model,
            max_tokens=SUMMARY_MAX_TOKENS,
            system=prompts.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompts.build_user_prompt(text)}],
        ) as stream:
            async for delta in stream.text_stream:
                if delta:
                    yield _sse("token", {"text": delta})
        yield _sse("done", {"summary_id": f"sum_{uuid.uuid4().hex[:12]}"})
    except Exception as e:  # upstream Anthropic / réseau
        log.exception("Summary upstream failed")
        yield _sse("error", {"code": "upstream_error", "message": str(e)})


@router.post("/v1/summary")
async def summary(req: SummaryRequest, user: User = Depends(require_user)):
    if not user.cloud_summary:
        raise ApiError("forbidden", "Votre plan n'inclut pas le résumé cloud.", 403)
    if anthropic_api_key() is None:
        raise ApiError("internal", "Backend mal configuré (clé Anthropic absente).", 500)

    text = prompts.prepare_transcription([e.model_dump() for e in req.entries])
    if text is None:
        raise ApiError("bad_request", "Transcription trop courte pour être résumée.", 400)

    model = resolve_model(req.model)
    return StreamingResponse(
        _stream_summary(text, model),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
