"""Fenêtre d'historique : lecture, export et effacement par réunion."""

import json

import pytest
from PyQt6.QtWidgets import QMessageBox

from benji import meetings
from benji.ui.history_window import HistoryWindow


@pytest.fixture
def window(qtbot):
    w = HistoryWindow()
    qtbot.addWidget(w)
    return w


def _shown(window) -> str:
    return window.transcript.plain_text()


def test_sans_reunion_l_ecran_est_vide(window):
    assert window.meeting_list.count() == 0
    assert _shown(window) == ""
    assert window.transcript.empty.isVisible() or not window.transcript.scroll.isVisible()
    assert not window.copy_btn.isEnabled()


def test_la_reunion_en_cours_est_selectionnee(window):
    window.history.add("Bonjour.", speaker="A")
    window.reload_meetings()

    assert window.meeting_list.count() == 1
    assert window._meeting_id == meetings.current_meeting_id()
    assert "Bonjour." in _shown(window)


def test_chaque_reunion_montre_ses_propres_entrees(window):
    window.history.add("Dans la première.")
    first = meetings.current_meeting_id()
    meetings.start_meeting("Deuxième")
    window.history.add("Dans la seconde.")
    window.reload_meetings()

    assert "Dans la seconde." in _shown(window)
    assert "Dans la première." not in _shown(window)

    window.meeting_list.setCurrentRow(window._row_for(first))
    assert "Dans la première." in _shown(window)
    assert "Dans la seconde." not in _shown(window)


def test_changer_de_reunion_oublie_les_noms_de_locuteurs(window):
    window.history.add("Bonjour.", speaker="A")
    first = meetings.current_meeting_id()
    meetings.start_meeting()
    window.history.add("Salut.", speaker="A")
    window.reload_meetings()
    window._speaker_names = {"A": "Alice"}

    # « A » n'est pas la même personne d'une réunion à l'autre.
    window.meeting_list.setCurrentRow(window._row_for(first))
    assert window._speaker_names == {}


def test_les_entrees_heritees_restent_lisibles(window):
    window.history.history_file.write_text(
        json.dumps({"timestamp": "2026-01-01T10:00:00", "text": "Ancienne réunion."}) + "\n",
        encoding="utf-8",
    )
    window.history.add("Nouvelle.")
    window.reload_meetings()

    row = window._row_for(meetings.LEGACY_ID)
    assert row >= 0
    window.meeting_list.setCurrentRow(row)
    assert "Ancienne réunion." in _shown(window)
    # Groupe hérité : pas de titre à renommer.
    assert not window.rename_meeting_btn.isEnabled()


def test_nouvelle_reunion_depuis_la_fenetre(window):
    window.history.add("Avant.")
    first = meetings.current_meeting_id()
    window.reload_meetings()

    window._new_meeting()

    assert meetings.current_meeting_id() != first
    assert window._meeting_id == meetings.current_meeting_id()
    assert window.meeting_list.count() == 2


def test_effacer_ne_touche_que_la_reunion_affichee(window, monkeypatch):
    window.history.add("À garder.")
    first = meetings.current_meeting_id()
    second = meetings.start_meeting().id
    window.history.add("À effacer.")
    window.reload_meetings()

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.clear_history()

    assert window.history.get_for_meeting(first) != []
    assert window.history.get_for_meeting(second) == []
    assert meetings.store().get(second) is None


def test_effacer_demande_confirmation(window, monkeypatch):
    window.history.add("À garder.")
    window.reload_meetings()

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Cancel)
    window.clear_history()

    assert window._entries != []


def test_le_nom_de_fichier_d_export_suit_le_titre(window):
    window.history.add("Bonjour.")
    meetings.store().rename(meetings.current_meeting_id(), "Point Produit / Q3")
    window.reload_meetings()

    assert window._meeting_slug() == "point-produit-q3"


# --- recherche ---


def test_la_recherche_filtre_la_liste_des_reunions(window):
    window.history.add("On parle du budget.")
    meetings.start_meeting("Autre sujet")
    window.history.add("On parle de la livraison.")
    window.reload_meetings()
    assert window.meeting_list.count() == 2

    window.search.setText("budget")

    assert window.meeting_list.count() == 1


def test_la_recherche_filtre_aussi_le_compte_rendu(window):
    window.history.add("On parle du budget.")
    window.history.add("Et de la livraison.")
    window.reload_meetings()

    window.search.setText("budget")

    assert "budget" in _shown(window)
    assert "livraison" not in _shown(window)


def test_la_recherche_annonce_le_nombre_de_resultats(window):
    window.history.add("Le budget est validé.")
    window.history.add("Rien à voir.")
    window.reload_meetings()

    window.search.setText("budget")

    assert window.meta_label.text() == "1 résultat sur 2"


def test_effacer_la_recherche_rend_tout(window):
    window.history.add("On parle du budget.")
    window.history.add("Et de la livraison.")
    window.reload_meetings()
    window.search.setText("budget")

    window.search.setText("")

    assert "livraison" in _shown(window)
    assert window.meeting_list.count() == 1


def test_une_reunion_est_trouvee_par_son_titre(window):
    window.history.add("Contenu quelconque.")
    meetings.store().rename(meetings.current_meeting_id(), "Point produit")
    window.reload_meetings()

    window.search.setText("produit")

    assert window.meeting_list.count() == 1
