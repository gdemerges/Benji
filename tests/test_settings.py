"""UserSettings : persistance + hydratation des dataclasses de config.

QSettings est injecté en IniFormat vers un fichier temporaire — aucun accès aux
préférences réelles de l'utilisateur, aucun QApplication requis.
"""

from PyQt6.QtCore import QSettings

from benji.config import STTConfig, UIConfig
from benji.settings import UserSettings


def _settings(tmp_path):
    path = str(tmp_path / "prefs.ini")
    return UserSettings(QSettings(path, QSettings.Format.IniFormat))


def test_roundtrip_int_and_bool(tmp_path):
    s = _settings(tmp_path)
    s.set_value("font_size", 42)
    s.set_value("diarization", False)
    assert s.get("font_size") == 42
    assert s.get("diarization") is False


def test_nullable_language_none_roundtrips(tmp_path):
    s = _settings(tmp_path)
    s.set_value("language", None)  # détection automatique
    assert s.get("language") is None


def test_get_missing_returns_default(tmp_path):
    s = _settings(tmp_path)
    assert s.get("font_size", default=28) == 28


def test_hydrate_applies_saved_values(tmp_path):
    s = _settings(tmp_path)
    s.set_value("model_size", "small")
    s.set_value("language", "en")
    s.set_value("bg_opacity", 200)

    stt, ui = STTConfig(), UIConfig()
    s.hydrate(stt=stt, ui=ui)

    assert stt.model_size == "small"
    assert stt.language == "en"
    assert ui.bg_opacity == 200


def test_hydrate_leaves_defaults_for_missing_keys(tmp_path):
    s = _settings(tmp_path)
    ui = UIConfig()
    default_font_size = ui.font_size
    s.hydrate(ui=ui)
    assert ui.font_size == default_font_size


def test_hydrate_language_empty_string_means_auto(tmp_path):
    s = _settings(tmp_path)
    s.set_value("language", None)
    stt = STTConfig()
    assert stt.language == "fr"  # défaut
    s.hydrate(stt=stt)
    assert stt.language is None  # détection automatique
