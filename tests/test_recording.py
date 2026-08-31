"""Écouter et garder ne sont pas le même geste.

Benji transcrit dès le lancement — on n'a jamais « oublié de lancer
l'enregistrement » — mais rien ne part sur disque sans accord, sinon une
conversation de couloir finit dans l'historique d'un produit vendu sur la
maîtrise de ses propres réunions.
"""

from __future__ import annotations

from benji import recording
from benji.recording import RecordingConsent


class FakeHistory:
    def __init__(self):
        self.rows: list[tuple[str, str | None]] = []

    def add(self, text: str, speaker: str | None = None) -> None:
        self.rows.append((text, speaker))


def test_rien_nest_ecrit_avant_laccord():
    h = FakeHistory()
    c = RecordingConsent(h)

    c.add("Ce que dit le couloir.", "Alice")

    assert h.rows == []
    assert c.pending_count == 1


def test_laccord_verse_ce_qui_a_deja_ete_dit():
    """C'est tout l'intérêt face à un bouton « démarrer » : on peut décider de
    garder la réunion trois minutes après qu'elle a commencé."""
    h = FakeHistory()
    c = RecordingConsent(h)
    c.add("Premier point.", "Alice")
    c.add("Deuxième point.", "Bob")

    versees = c.arm()

    assert versees == 2
    assert h.rows == [("Premier point.", "Alice"), ("Deuxième point.", "Bob")]
    assert c.pending_count == 0


def test_apres_laccord_lecriture_est_directe():
    h = FakeHistory()
    c = RecordingConsent(h)
    c.arm()

    c.add("La suite.", None)

    assert h.rows == [("La suite.", None)]
    assert c.pending_count == 0


def test_reaccorder_ne_reecrit_rien():
    h = FakeHistory()
    c = RecordingConsent(h)
    c.add("Une ligne.")
    c.arm()

    assert c.arm() == 0
    assert h.rows == [("Une ligne.", None)]


def test_arme_des_le_depart_quand_la_confirmation_est_desactivee():
    h = FakeHistory()
    c = RecordingConsent(h, armed=True)

    c.add("Tout est conservé d'office.")

    assert h.rows == [("Tout est conservé d'office.", None)]


def test_une_nouvelle_reunion_redemande_laccord():
    """Avoir accepté de garder celle de ce matin ne dit rien de la suivante."""
    h = FakeHistory()
    c = RecordingConsent(h)
    c.arm()

    c.reset()

    c.add("Réunion suivante.")
    assert not c.armed
    assert h.rows == []


def test_la_remise_a_zero_abandonne_lattente():
    """Ce qui restait en attente appartenait à la réunion qu'on vient de quitter."""
    h = FakeHistory()
    c = RecordingConsent(h)
    c.add("Non demandé.")

    c.reset()
    c.arm()

    assert h.rows == []


def test_lattente_est_bornee(monkeypatch):
    """Benji laissé ouvert toute la journée sans accord ne doit pas gonfler."""
    monkeypatch.setattr(recording, "_MAX_PENDING", 3)
    h = FakeHistory()
    c = RecordingConsent(h)

    for i in range(10):
        c.add(f"ligne {i}")

    assert c.pending_count == 3
    c.arm()
    # Ce sont les plus récentes qui survivent.
    assert [t for t, _ in h.rows] == ["ligne 7", "ligne 8", "ligne 9"]


def test_le_contenu_ne_fuite_pas_dans_les_logs(caplog):
    """Le log part dans les rapports de bug : le compte, jamais le texte."""
    import logging

    h = FakeHistory()
    c = RecordingConsent(h)
    c.add("Le client s'appelle Dupont et le budget est de 40 000 €.")

    with caplog.at_level(logging.DEBUG):
        c.arm()

    assert "Dupont" not in caplog.text
    assert "40 000" not in caplog.text
