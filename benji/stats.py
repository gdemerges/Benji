"""Session statistics: segment count, audio seconds, transcription latency."""

from __future__ import annotations

import threading
from collections import Counter, deque
from datetime import datetime


class SessionStats:
    def __init__(self, max_latency_samples: int = 500):
        self.session_start = datetime.now()
        self._lock = threading.Lock()
        self._segments = 0
        self._audio_seconds = 0.0
        self._final_latencies_ms: deque[float] = deque(maxlen=max_latency_samples)
        self._partial_latencies_ms: deque[float] = deque(maxlen=max_latency_samples)
        self._partial_count = 0
        self._drops: Counter[str] = Counter()

    def record_drop(self, reason: str) -> None:
        """Count an event where audio (or a transcription) was lost.

        Reasons include "transcribe_queue_full" (VAD couldn't enqueue a final
        segment), "stt_error" (a segment crashed), "stt_thread_restart" (the
        supervisor relaunched the STT thread).
        """
        with self._lock:
            self._drops[reason] += 1

    def record_segment(
        self,
        audio_seconds: float,
        latency_ms: float,
        is_final: bool = True,
    ) -> None:
        with self._lock:
            if is_final:
                self._segments += 1
                self._audio_seconds += audio_seconds
                self._final_latencies_ms.append(latency_ms)
            else:
                self._partial_count += 1
                self._partial_latencies_ms.append(latency_ms)

    @staticmethod
    def _percentiles(values: deque[float]) -> tuple[float, float]:
        s = sorted(values)
        n = len(s)
        if n == 0:
            return 0.0, 0.0
        return s[n // 2], s[max(0, int(n * 0.95) - 1)]

    def snapshot(self) -> dict:
        with self._lock:
            p50, p95 = self._percentiles(self._final_latencies_ms)
            pp50, pp95 = self._percentiles(self._partial_latencies_ms)
            duration = (datetime.now() - self.session_start).total_seconds()
            return {
                "session_duration_s": duration,
                "segments": self._segments,
                "audio_seconds": self._audio_seconds,
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "partials": self._partial_count,
                "partial_latency_p50_ms": pp50,
                "partial_latency_p95_ms": pp95,
                "drops": dict(self._drops),
            }

    def format_footer(self) -> str:
        s = self.snapshot()
        mins = s["session_duration_s"] / 60
        line = (
            f"Session: {mins:.1f} min · {s['segments']} segments · "
            f"{s['audio_seconds']:.0f}s audio · "
            f"final p50={s['latency_p50_ms']:.0f}ms p95={s['latency_p95_ms']:.0f}ms"
        )
        if s["partials"]:
            line += (
                f" · partial×{s['partials']} "
                f"p50={s['partial_latency_p50_ms']:.0f}ms p95={s['partial_latency_p95_ms']:.0f}ms"
            )
        if s["drops"]:
            drops_str = ", ".join(f"{k}={v}" for k, v in sorted(s["drops"].items()))
            line += f" · drops[{drops_str}]"
        return line
