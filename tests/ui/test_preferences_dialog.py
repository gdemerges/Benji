"""PreferencesDialog : construction + persistance/application au clic « Save »."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from benji.config import LLMConfig, STTConfig, UIConfig
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


def test_providers_hidden_without_llm_config(qapp, tmp_path):
    from benji.ui.preferences_dialog import PreferencesDialog

    dlg = PreferencesDialog(STTConfig(), UIConfig(), _settings(tmp_path))
    assert dlg._engine_box is None
    dlg.close()


def test_save_persists_providers(qapp, tmp_path):
    from benji.ui.preferences_dialog import PreferencesDialog

    stt, ui, llm = STTConfig(), UIConfig(), LLMConfig()
    settings = _settings(tmp_path)

    dlg = PreferencesDialog(stt, ui, settings, llm_config=llm)
    dlg._select_data(dlg._stt_provider, "remote")
    dlg._select_data(dlg._summary_provider, "remote")
    dlg._save()

    # Config vivante mise à jour (effet réel au prochain démarrage)
    assert stt.stt_provider == "remote"
    assert llm.summary_provider == "remote"

    # Persisté : une nouvelle hydratation retrouve les valeurs
    stt2, llm2 = STTConfig(), LLMConfig()
    settings.hydrate(stt=stt2, llm=llm2)
    assert stt2.stt_provider == "remote"
    assert llm2.summary_provider == "remote"


def test_provider_combo_keeps_unknown_value(qapp, tmp_path):
    """Un provider hors liste (ex. « cloud » en dev) n'est pas écrasé au save."""
    from benji.ui.preferences_dialog import PreferencesDialog

    llm = LLMConfig(summary_provider="cloud")
    dlg = PreferencesDialog(STTConfig(), UIConfig(), _settings(tmp_path), llm_config=llm)
    assert dlg._summary_provider.currentData() == "cloud"
    dlg._save()
    assert llm.summary_provider == "cloud"
    dlg.close()
