"""Panneau Préférences : réglages transcription + affichage, persistés.

Modal, sur le thread Qt. Chaque changement validé est écrit dans `UserSettings`
(QSettings) et appliqué à la config vivante. Les réglages d'affichage sont
poussés à chaud sur l'overlay via `on_live_change` ; ceux de transcription ne
prennent effet qu'au prochain lancement — un bandeau le signale si l'un d'eux a
changé.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFontComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from benji.settings import UserSettings

# (code langue Whisper, libellé). "" = détection automatique.
_LANGUAGES = [
    ("", "Détection automatique"),
    ("fr", "Français"),
    ("en", "English"),
    ("es", "Español"),
    ("de", "Deutsch"),
    ("it", "Italiano"),
    ("pt", "Português"),
    ("nl", "Nederlands"),
]

_MODEL_SIZES = ["base", "small", "medium", "large-v3"]

# (secondes, libellé). 0 = désactivé.
_SUMMARY_INTERVALS = [
    (0, "Désactivé"),
    (300, "Toutes les 5 min"),
    (600, "Toutes les 10 min"),
    (900, "Toutes les 15 min"),
]


class PreferencesDialog(QDialog):
    def __init__(
        self,
        stt_config,
        ui_config,
        settings: UserSettings,
        on_live_change: Callable[[object], None] | None = None,
        parent=None,
    ):
        """on_live_change: reçoit une UIConfig mise à jour pour application à chaud
        (typiquement `overlay.apply_config`)."""
        super().__init__(parent)
        self._stt = stt_config
        self._ui = ui_config
        self._settings = settings
        self._on_live_change = on_live_change
        self.setWindowTitle("Préférences Benji")
        self.setModal(True)
        self.setMinimumWidth(380)

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # === Transcription (redémarrage requis) ===
        stt_box = QGroupBox("Transcription")
        stt_form = QFormLayout(stt_box)

        self._language = QComboBox()
        for code, label in _LANGUAGES:
            self._language.addItem(label, code)
        self._select_data(self._language, self._stt.language or "")
        stt_form.addRow("Langue", self._language)

        self._model = QComboBox()
        self._model.addItems(_MODEL_SIZES)
        if self._stt.model_size in _MODEL_SIZES:
            self._model.setCurrentText(self._stt.model_size)
        stt_form.addRow("Modèle Whisper", self._model)

        self._diarization = QCheckBox("Identifier les locuteurs")
        self._diarization.setChecked(bool(self._stt.diarization))
        stt_form.addRow("Diarisation", self._diarization)

        self._summary = QComboBox()
        for secs, label in _SUMMARY_INTERVALS:
            self._summary.addItem(label, secs)
        self._select_data(self._summary, self._stt.live_summary_interval_s)
        stt_form.addRow("Résumé en direct", self._summary)

        hint = QLabel("Ces réglages prennent effet au prochain démarrage.")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        stt_form.addRow(hint)
        layout.addWidget(stt_box)

        # === Affichage (application immédiate) ===
        ui_box = QGroupBox("Affichage")
        ui_form = QFormLayout(ui_box)

        self._font = QFontComboBox()
        self._font.setCurrentFont(QFont(self._ui.font_family))
        ui_form.addRow("Police", self._font)

        self._font_size = QSpinBox()
        self._font_size.setRange(10, 96)
        self._font_size.setSuffix(" px")
        self._font_size.setValue(int(self._ui.font_size))
        ui_form.addRow("Taille", self._font_size)

        self._opacity = QSpinBox()
        self._opacity.setRange(0, 255)
        self._opacity.setValue(int(self._ui.bg_opacity))
        ui_form.addRow("Opacité du fond", self._opacity)

        self._duration = QSpinBox()
        self._duration.setRange(1, 60)
        self._duration.setSuffix(" s")
        self._duration.setValue(round(int(self._ui.display_duration_ms) / 1000))
        ui_form.addRow("Durée d'affichage", self._duration)

        layout.addWidget(ui_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _select_data(combo: QComboBox, data) -> None:
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _save(self) -> None:
        s = self._settings

        # --- Transcription : persister + mettre à jour la config (effet au reboot) ---
        language = self._language.currentData() or None
        model_size = self._model.currentText()
        diarization = self._diarization.isChecked()
        summary_interval = self._summary.currentData()

        s.set_value("language", language)
        s.set_value("model_size", model_size)
        s.set_value("diarization", diarization)
        s.set_value("live_summary_interval_s", summary_interval)
        self._stt.language = language
        self._stt.model_size = model_size
        self._stt.diarization = diarization
        self._stt.live_summary_interval_s = summary_interval

        # --- Affichage : persister + appliquer à chaud ---
        font_family = self._font.currentFont().family()
        font_size = self._font_size.value()
        bg_opacity = self._opacity.value()
        display_ms = self._duration.value() * 1000

        s.set_value("font_family", font_family)
        s.set_value("font_size", font_size)
        s.set_value("bg_opacity", bg_opacity)
        s.set_value("display_duration_ms", display_ms)
        self._ui.font_family = font_family
        self._ui.font_size = font_size
        self._ui.bg_opacity = bg_opacity
        self._ui.display_duration_ms = display_ms

        if self._on_live_change is not None:
            # Copie figée pour que l'overlay reçoive un snapshot cohérent.
            self._on_live_change(replace(self._ui))

        self.accept()
