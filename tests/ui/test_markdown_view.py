"""Les résumés s'affichent composés — jamais en markdown source."""

from __future__ import annotations

from datetime import datetime

from benji.ui.live_summary_window import LiveSummaryWindow
from benji.ui.widgets.markdown_view import MarkdownView


def test_le_markdown_est_rendu_pas_recopie(qtbot):
    view = MarkdownView()
    qtbot.addWidget(view)
    view.set_markdown("**Décision** : sortie le 22.\n\n- Build prêt.")

    shown = view.toPlainText()
    assert "Décision" in shown
    assert "**" not in shown  # les astérisques ne doivent jamais rester visibles


def test_resume_live_rend_le_markdown_recu_en_bloc(qtbot):
    w = LiveSummaryWindow()
    qtbot.addWidget(w)
    w.on_summary("**Décision** : le 22.", datetime(2026, 8, 21, 14, 30))

    assert "**" not in w.view.toPlainText()
    assert "Décision" in w.view.toPlainText()
    assert w.stamp.text() == "14:30"


def test_resume_live_recompose_pendant_le_streaming(qtbot):
    w = LiveSummaryWindow()
    qtbot.addWidget(w)
    w.on_summary_start(datetime(2026, 8, 21, 14, 30))
    w.on_summary_chunk("**Déci")
    w.on_summary_chunk("sion** : le 22.")
    w.on_summary("", datetime(2026, 8, 21, 14, 31))

    shown = w.view.toPlainText()
    assert "Décision : le 22." in shown
    assert "**" not in shown
