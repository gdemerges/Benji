"""File d'affichage qui **prévient** son consommateur au lieu d'être sondée.

`DisplayBus` interrogeait `display_queue` toutes les 16 ms, en permanence : 62
réveils par seconde même micro en pause, sur une app faite pour rester ouverte
toute la journée sur batterie. Sonder plus lentement aurait retardé le premier
mot d'un énoncé — précisément ce qu'on ne veut pas ralentir.

Le producteur signale donc lui-même qu'il a écrit. Le rappel est appelé **sur le
thread producteur** (STT, VAD) : il doit être non bloquant — côté Qt il ne fait
qu'émettre un signal, ce qui poste un événement et rend la main.

Sans Qt ici : `benji/app.py` construit le pipeline avant même le QApplication.
"""

from __future__ import annotations

import logging
from queue import Queue

log = logging.getLogger(__name__)


class NotifyingQueue(Queue):
    """`Queue` qui appelle un rappel après chaque écriture réussie."""

    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize=maxsize)
        self._listener = None

    def set_listener(self, listener) -> None:
        """Pose (ou retire avec `None`) le rappel de réveil."""
        self._listener = listener

    def _notify(self) -> None:
        listener = self._listener
        if listener is None:
            return
        try:
            listener()
        except Exception:
            # Un consommateur cassé ne doit jamais faire échouer une écriture :
            # le pipeline audio continue, quitte à ce que l'affichage attende le
            # filet de sécurité du bus.
            log.exception("Réveil du consommateur en échec")

    def put(self, item, block=True, timeout=None):
        # Seul `put` est redéfini : `Queue.put_nowait` lui délègue, le redéfinir
        # aussi notifierait deux fois par écriture.
        super().put(item, block=block, timeout=timeout)
        self._notify()
