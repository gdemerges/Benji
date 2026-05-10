"""Centralized logging setup.

Each module gets its logger via `logging.getLogger(__name__)`. The console
handler emits a short, colorized-friendly format that mirrors the legacy
`[Tag] message` style by using the logger's *short* name as the tag.

Verbosity is controlled by env var `BENJI_LOG_LEVEL` (default INFO). Set to
DEBUG for verbose troubleshooting, WARNING to silence routine messages.
"""

from __future__ import annotations

import logging
import os
import sys


_TAG_BY_MODULE = {
    "benji.main": "Benji",
    "benji.audio.capture": "Audio",
    "benji.audio.vad": "VAD",
    "benji.stt.backend": "STT",
    "benji.stt.transcriber": "STT",
    "benji.stt.diarization": "Diarization",
    "benji.llm.summarizer": "Summary",
    "benji.llm.live_summary": "LiveSummary",
    "benji.llm.corrector": "LLM",
    "benji.ui.overlay": "UI",
    "benji.ui.splash": "UI",
}


class _TagFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        tag = _TAG_BY_MODULE.get(record.name, record.name.split(".")[-1])
        record.tag = tag
        return super().format(record)


_configured = False


def setup_logging(level: str | None = None) -> None:
    """Configure the root `benji` logger. Idempotent."""
    global _configured
    if _configured:
        return
    _configured = True

    resolved = (level or os.environ.get("BENJI_LOG_LEVEL") or "INFO").upper()

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_TagFormatter("[%(tag)s] %(message)s"))

    root = logging.getLogger("benji")
    root.setLevel(resolved)
    root.addHandler(handler)
    root.propagate = False
