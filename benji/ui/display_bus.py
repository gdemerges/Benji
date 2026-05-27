"""Hub Qt qui draine display_queue et émet un signal multi-consumer.

Permet à plusieurs widgets (overlay + LiveTab) de réagir aux mêmes events
sans dupliquer la lecture de la queue.
"""

from __future__ import annotations

import logging
from queue import Empty, Queue

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger(__name__)


class DisplayBus(QObject):
    event = pyqtSignal(object)  # le signal porte un dict ou un str

    def __init__(self, queue: Queue, poll_ms: int = 16, parent=None):
        super().__init__(parent)
        self._queue = queue
        # Note: QTimer must not have `self` as parent in PyQt6 6.10+ due to a
        # regression where emitting a signal inside a child-QTimer callback raises
        # "native Qt signal is not callable". Keeping an explicit reference prevents GC.
        self._timer = QTimer()
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._drain)
        self._stopped = False

    def start(self) -> None:
        self._stopped = False
        self._timer.start()

    def stop(self) -> None:
        self._stopped = True
        self._timer.stop()

    def subscribe(self, slot) -> None:
        """Subscribe a slot with crash isolation. Préférable à event.connect direct."""
        def _wrapped(item):
            try:
                slot(item)
            except Exception:
                log.exception("DisplayBus subscriber raised")
        self.event.connect(_wrapped)

    def _drain(self) -> None:
        if self._stopped:
            return
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                return
            if item is None:
                continue
            self._emit_safe(item)

    def _emit_safe(self, item) -> None:
        try:
            self.event.emit(item)
        except Exception:
            log.exception("DisplayBus subscriber raised")
