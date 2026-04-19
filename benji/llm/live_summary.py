"""Background thread that periodically summarizes recent transcription."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable

from benji.history import TranscriptionHistory
from benji.llm.summarizer import summarize


class LiveSummarizer:
    def __init__(
        self,
        interval_seconds: int,
        session_start: datetime,
        on_summary: Callable[[str, datetime], None],
        min_new_entries: int = 3,
    ):
        self.interval = interval_seconds
        self.session_start = session_start
        self.on_summary = on_summary
        self.min_new_entries = min_new_entries
        self.history = TranscriptionHistory()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run_at = session_start

    def start(self) -> None:
        if self.interval <= 0:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="LiveSummary")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                entries = self.history.get_since(self._last_run_at)
                if len(entries) < self.min_new_entries:
                    continue
                summary = summarize(entries)
                if summary:
                    now = datetime.now()
                    self.on_summary(summary, now)
                    self._last_run_at = now
            except Exception as e:
                print(f"[LiveSummary] Error: {e}")
