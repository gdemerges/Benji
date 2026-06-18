"""GrokSTTSession : traduction des messages xAI → events du contrat (sans réseau)."""

import asyncio

from app.stt.grok import GrokSTTSession


def _drain(messages: list[dict]) -> list[dict]:
    """Joue une séquence de messages Grok et renvoie les events émis."""
    async def run():
        s = GrokSTTSession(api_key="k")
        for m in messages:
            await s._translate(m)
        await s._emit_done()
        return [e async for e in s.events()]

    return asyncio.run(run())


def test_interim_then_final_with_speaker():
    events = _drain([
        {"type": "transcript.created"},
        {"type": "transcript.partial", "text": "bonjour le", "is_final": False},
        {"type": "transcript.partial", "text": "bonjour le monde", "is_final": False},
        {"type": "transcript.done", "text": "Bonjour le monde",
         "words": [{"text": "Bonjour", "speaker": 1}]},
    ])

    assert events == [
        {"type": "vad_status", "speaking": True},
        {"type": "segment_start"},
        {"type": "word", "text": "bonjour"},
        {"type": "word", "text": "le"},
        {"type": "word", "text": "monde"},
        {"type": "final_text", "text": "Bonjour le monde", "speaker": "B"},  # speaker 1 → B
        {"type": "vad_status", "speaking": False},
    ]


def test_final_without_diarization_has_no_speaker():
    events = _drain([
        {"type": "transcript.partial", "text": "salut"},
        {"type": "transcript.done", "text": "Salut", "words": [{"text": "Salut"}]},
    ])
    final = [e for e in events if e["type"] == "final_text"][0]
    assert "speaker" not in final


def test_empty_transcript_ignored():
    events = _drain([{"type": "transcript.partial", "text": "   "}])
    assert events == []  # rien à relayer, pas de segment ouvert
