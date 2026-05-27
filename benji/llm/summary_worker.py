"""QThread async qui exécute summarize() + save_summary() sans bloquer l'UI."""

from __future__ import annotations

import logging
from pathlib import Path
from queue import Queue

from PyQt6.QtCore import QThread, pyqtSignal

from benji.llm.summarizer import save_summary, summarize

log = logging.getLogger(__name__)

_STOP_SENTINEL = object()


class SummaryWorker(QThread):
    started = pyqtSignal(str)               # summary_id
    chunk = pyqtSignal(str, str)            # summary_id, token chunk
    finished = pyqtSignal(str, object)      # summary_id, Path
    failed = pyqtSignal(str, str)           # summary_id, error message

    def __init__(self, language: str = "fr", parent=None):
        super().__init__(parent)
        self._queue: Queue = Queue()
        self._language = language
        self.setObjectName("SummaryWorker")

    def request(self, text: str, summary_id: str) -> None:
        """Thread-safe : enqueue une demande de résumé."""
        self._queue.put((summary_id, text))

    def shutdown(self) -> None:
        self._queue.put(_STOP_SENTINEL)
        self.wait(5000)

    def run(self) -> None:
        log.info("SummaryWorker started")
        while True:
            item = self._queue.get()
            if item is _STOP_SENTINEL:
                break
            sid, text = item
            self.started.emit(sid)
            try:
                full = summarize(
                    text,
                    language=self._language,
                    on_token=lambda c, _sid=sid: self.chunk.emit(_sid, c),
                )
                path = save_summary(full)
                self.finished.emit(sid, path)
            except Exception as e:
                log.exception("Summary failed for %s", sid)
                self.failed.emit(sid, str(e))
        log.info("SummaryWorker stopped")
