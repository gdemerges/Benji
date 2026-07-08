"""PreferencesDialog : construction + persistance/application au clic « Save »."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from benji.config import STTConfig, UIConfig
from benji.settings import UserSettings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _settings(tmp_path):
    return UserSettings(QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat))


def test_dialog_instantiates(qapp, tmp_path):
    from benji.ui.preferences_dialog import PreferencesDialog

    dlg = PreferencesDialog(STTConfig(), UIConfig(), _settings(tmp_path))
    assert dlg.windowTitle() == "Préférences Benji"
    dlg.close()


def test_save_persists_and_applies_live(qapp, tmp_path):
    from benji.ui.preferences_dialog import PreferencesDialog

    stt, ui = STTConfig(), UIConfig()
    settings = _settings(tmp_path)
    applied: list = []

    dlg = PreferencesDialog(stt, ui, settings, on_live_change=applied.append)
    dlg._font_size.setValue(40)
    dlg._opacity.setValue(120)
    dlg._model.setCurrentText("small")
    dlg._save()

    # Config vivante mise à jour
    assert ui.font_size == 40
    assert ui.bg_opacity == 120
    assert stt.model_size == "small"

    # Réglage live poussé via le callback
    assert applied and applied[0].font_size == 40

    # Persisté : une nouvelle hydratation retrouve les valeurs
    stt2, ui2 = STTConfig(), UIConfig()
    settings.hydrate(stt=stt2, ui=ui2)
    assert ui2.font_size == 40
    assert stt2.model_size == "small"
