"""Le fond des fenêtres est réellement peint — pas laissé au système.

Une feuille de style posée sur une `QMainWindow` (ou sur un `QWidget` dérivé)
n'est pas rendue tant que le widget ne réclame pas son fond stylé. Le symptôme
est sournois : à l'écran la fenêtre paraît normale, parce que macOS la remplit
avec **son** gris système — le plan de travail défini dans `style.py`
n'apparaissait nulle part, et l'app gardait le look générique qu'elle cherche
justement à quitter.

Ces tests lisent le pixel du fond, seul moyen de distinguer « peint dans notre
couleur » de « pas peint du tout ».
"""

from __future__ import annotations

from datetime import datetime

import pytest

from benji.ui.history_window import HistoryWindow
from benji.ui.live_summary_window import LiveSummaryWindow
from benji.ui.main_window import MainWindow
from benji.ui.style import current_theme


class _Signal:
    def connect(self, *args, **kwargs):
        pass


class _Bus:
    event = _Signal()

    def subscribe(self, slot):
        pass


class _Worker:
    started = failed = finished = chunk = _Signal()

    def request(self, **kwargs):
        pass


def _background_pixel(widget, x: int = 6, y: int = 260):
    widget.resize(600, 420)
    widget.show()
    return widget.grab().toImage().pixelColor(x, y)


@pytest.fixture
def windows(qtbot):
    from benji.history import TranscriptionHistory

    main = MainWindow(bus=_Bus(), history=TranscriptionHistory(),
                      session_start=datetime.now(), summary_worker=_Worker())
    history = HistoryWindow()
    summary = LiveSummaryWindow()
    for w in (main, history, summary):
        qtbot.addWidget(w)
    return main, history, summary


def test_les_fenetres_peignent_le_plan_de_travail(windows):
    paper = current_theme().paper
    for window in windows:
        pixel = _background_pixel(window)
        assert pixel.alpha() == 255, f"{type(window).__name__} : fond non peint"
        assert (pixel.red(), pixel.green(), pixel.blue()) == (
            paper.red(), paper.green(), paper.blue()
        ), f"{type(window).__name__} : fond {pixel.name()} au lieu de {paper.name()}"


def test_la_bande_de_toolbar_est_peinte_aussi(windows):
    """La toolbar vit hors du widget central : elle a son propre fond à peindre.

    Sans lui, une bande de gris système restait au-dessus du plan de travail.
    """
    main = windows[0]
    paper = current_theme().paper
    pixel = _background_pixel(main, x=300, y=26)

    assert pixel.alpha() == 255, "bande de toolbar non peinte"
    assert (pixel.red(), pixel.green(), pixel.blue()) == (
        paper.red(), paper.green(), paper.blue()
    )


def test_la_feuille_se_detache_du_plan(windows):
    """Le relief tient à un écart réel entre les deux plans."""
    theme = current_theme()
    assert theme.sheet.name() != theme.paper.name()
    # La feuille est plus claire que le plan en thème clair, et l'inverse tient
    # en sombre : c'est elle qui porte le relief, pas l'ombre.
    if theme.is_dark:
        assert theme.sheet.lightness() > theme.paper.lightness()
    else:
        assert theme.sheet.lightness() > theme.paper.lightness()
