"""Hub Qt qui draine display_queue et émet un signal multi-consumer.

Permet à plusieurs widgets (overlay + LiveTab) de réagir aux mêmes events
sans dupliquer la lecture de la queue.

**Réveillé, pas sondé.** Une `NotifyingQueue` (cf. `benji/queues.py`) prévient le
bus depuis le thread producteur ; le drainage est alors immédiat au lieu
d'attendre le prochain tick, et l'app ne réveille plus le CPU 62 fois par
seconde pour trouver une file vide. Le minuteur reste, au ralenti : filet de
sécurité si la file n'est pas notifiante (tests, file simple).
"""

from __future__ import annotations

import logging
from queue import Empty, Queue

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal

log = logging.getLogger(__name__)

# Cadence du filet de sécurité quand la file réveille le bus elle-même. Assez
# lent pour ne rien coûter à vide, assez fréquent pour qu'un réveil perdu ne se
# voie pas.
_SAFETY_POLL_MS = 250


class DisplayBus(QObject):
    event = pyqtSignal(object)  # le signal porte un dict ou un str
    # Réveil venu d'un thread producteur. Passer par un signal est ce qui rend
    # la notification sûre : l'émission poste un événement et rend la main, le
    # drainage a lieu sur le thread Qt.
    _wake = pyqtSignal()

    def __init__(self, queue: Queue, poll_ms: int = 16, parent=None):
        super().__init__(parent)
        self._queue = queue
        self._notifying = hasattr(queue, "set_listener")
        if self._notifying:
            self._wake.connect(self._drain, Qt.ConnectionType.QueuedConnection)
            poll_ms = _SAFETY_POLL_MS
        # Note: QTimer must not have `self` as parent in PyQt6 6.10+ due to a
        # regression where emitting a signal inside a child-QTimer callback raises
        # "native Qt signal is not callable". Keeping an explicit reference prevents GC.
        self._timer = QTimer()
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._drain)
        self._stopped = False

    def start(self) -> None:
        self._stopped = False
        if self._notifying:
            self._queue.set_listener(self._wake.emit)
        self._timer.start()

    def stop(self) -> None:
        self._stopped = True
        if self._notifying:
            self._queue.set_listener(None)
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
