"""Session statistics: segment count, audio seconds, transcription latency."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime


class SessionStats:
    def __init__(self, max_latency_samples: int = 500):
        self.session_start = datetime.now()
        self._lock = threading.Lock()
        self._segments = 0
        self._audio_seconds = 0.0
        self._latencies_ms: deque[float] = deque(maxlen=max_latency_samples)

    def record_segment(self, audio_seconds: float, latency_ms: float) -> None:
        with self._lock:
            self._segments += 1
            self._audio_seconds += audio_seconds
            self._latencies_ms.append(latency_ms)

    def snapshot(self) -> dict:
        with self._lock:
            latencies = sorted(self._latencies_ms)
            n = len(latencies)
            p50 = latencies[n // 2] if n else 0.0
            p95 = latencies[max(0, int(n * 0.95) - 1)] if n else 0.0
            duration = (datetime.now() - self.session_start).total_seconds()
            return {
                "session_duration_s": duration,
                "segments": self._segments,
                "audio_seconds": self._audio_seconds,
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
            }

    def format_footer(self) -> str:
        s = self.snapshot()
        mins = s["session_duration_s"] / 60
        return (
            f"Session: {mins:.1f} min · {s['segments']} segments · "
            f"{s['audio_seconds']:.0f}s audio · "
            f"latency p50={s['latency_p50_ms']:.0f}ms p95={s['latency_p95_ms']:.0f}ms"
        )
