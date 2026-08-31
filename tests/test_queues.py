"""`NotifyingQueue` : le producteur réveille le consommateur.

Le bus d'affichage sondait la file toutes les 16 ms en permanence — 62 réveils
par seconde même micro en pause. Sonder plus lentement aurait retardé le premier
mot d'un énoncé, donc c'est le producteur qui signale.
"""

from __future__ import annotations

import pytest

from benji.queues import NotifyingQueue


def test_chaque_ecriture_reveille_le_consommateur():
    q = NotifyingQueue()
    reveils = []
    q.set_listener(lambda: reveils.append(1))

    q.put({"type": "word"})
    q.put_nowait({"type": "final_text"})

    assert len(reveils) == 2


def test_sans_auditeur_la_file_reste_une_file():
    q = NotifyingQueue(maxsize=2)
    q.put("a")
    assert q.get() == "a"


def test_le_retrait_de_lauditeur_arrete_les_reveils():
    q = NotifyingQueue()
    reveils = []
    q.set_listener(lambda: reveils.append(1))
    q.set_listener(None)

    q.put("a")

    assert reveils == []


def test_un_consommateur_casse_ne_fait_pas_echouer_lecriture():
    """Le rappel court sur le thread producteur : l'audio ne doit rien risquer."""
    q = NotifyingQueue()
    q.set_listener(lambda: 1 / 0)

    q.put("a")  # ne lève pas

    assert q.get() == "a"


def test_la_file_reste_bornee():
    """Le réveil ne doit pas court-circuiter la contre-pression."""
    q = NotifyingQueue(maxsize=1)
    q.set_listener(lambda: None)
    q.put("a")
    with pytest.raises(Exception):
        q.put_nowait("b")
