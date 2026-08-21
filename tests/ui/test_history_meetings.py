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


def test_sans_reunion_l_ecran_est_vide(window):
    assert window.meeting_combo.count() == 0
    assert "Aucune transcription" in window.text_edit.toPlainText()
    assert not window.copy_btn.isEnabled()


def test_la_reunion_en_cours_est_selectionnee(window):
    window.history.add("Bonjour.", speaker="A")
    window.reload_meetings()

    assert window.meeting_combo.count() == 1
    assert window._meeting_id == meetings.current_meeting_id()
    assert "Bonjour." in window.text_edit.toPlainText()


def test_chaque_reunion_montre_ses_propres_entrees(window):
    window.history.add("Dans la première.")
    first = meetings.current_meeting_id()
    meetings.start_meeting("Deuxième")
    window.history.add("Dans la seconde.")
    window.reload_meetings()

    assert "Dans la seconde." in window.text_edit.toPlainText()
    assert "Dans la première." not in window.text_edit.toPlainText()

    window.meeting_combo.setCurrentIndex(window.meeting_combo.findData(first))
    assert "Dans la première." in window.text_edit.toPlainText()
    assert "Dans la seconde." not in window.text_edit.toPlainText()


def test_changer_de_reunion_oublie_les_noms_de_locuteurs(window):
    window.history.add("Bonjour.", speaker="A")
    first = meetings.current_meeting_id()
    meetings.start_meeting()
    window.history.add("Salut.", speaker="A")
    window.reload_meetings()
    window._speaker_names = {"A": "Alice"}

    # « A » n'est pas la même personne d'une réunion à l'autre.
    window.meeting_combo.setCurrentIndex(window.meeting_combo.findData(first))
    assert window._speaker_names == {}


def test_les_entrees_heritees_restent_lisibles(window):
    window.history.history_file.write_text(
        json.dumps({"timestamp": "2026-01-01T10:00:00", "text": "Ancienne réunion."}) + "\n",
        encoding="utf-8",
    )
    window.history.add("Nouvelle.")
    window.reload_meetings()

    index = window.meeting_combo.findData(meetings.LEGACY_ID)
    assert index >= 0
    window.meeting_combo.setCurrentIndex(index)
    assert "Ancienne réunion." in window.text_edit.toPlainText()
    # Groupe hérité : pas de titre à renommer.
    assert not window.rename_meeting_btn.isEnabled()


def test_nouvelle_reunion_depuis_la_fenetre(window):
    window.history.add("Avant.")
    first = meetings.current_meeting_id()
    window.reload_meetings()

    window._new_meeting()

    assert meetings.current_meeting_id() != first
    assert window._meeting_id == meetings.current_meeting_id()
    assert window.meeting_combo.count() == 2


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
