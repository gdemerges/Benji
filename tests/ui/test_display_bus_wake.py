"""DisplayBus : réveillé par la file, sondé seulement en filet de sécurité."""

from __future__ import annotations

from queue import Queue

from benji.queues import NotifyingQueue
from benji.ui.display_bus import _SAFETY_POLL_MS, DisplayBus


def test_une_file_notifiante_met_le_minuteur_au_ralenti(qtbot):
    bus = DisplayBus(NotifyingQueue())
    assert bus._timer.interval() == _SAFETY_POLL_MS


def test_une_file_simple_reste_sondee_vite(qtbot):
    """Tests et chemins tiers passent encore une `Queue` nue."""
    bus = DisplayBus(Queue(), poll_ms=16)
    assert bus._timer.interval() == 16


def test_une_ecriture_est_drainee_sans_attendre_le_tick(qtbot):
    q = NotifyingQueue()
    bus = DisplayBus(q)
    recus = []
    bus.subscribe(recus.append)
    bus.start()

    q.put({"type": "final_text", "text": "bonjour"})

    # Le réveil traverse la boucle d'événements Qt, pas le minuteur (250 ms).
    qtbot.waitUntil(lambda: recus != [], timeout=100)
    assert recus[0]["text"] == "bonjour"
    bus.stop()


def test_larret_du_bus_detache_lauditeur(qtbot):
    """Un bus arrêté ne doit plus être réveillé par le pipeline audio."""
    q = NotifyingQueue()
    bus = DisplayBus(q)
    bus.start()
    bus.stop()

    assert q._listener is None
