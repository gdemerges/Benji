"""Panneau Préférences : réglages transcription + affichage, persistés.

Modal, sur le thread Qt. Chaque changement validé est écrit dans `UserSettings`
(QSettings) et appliqué à la config vivante. Les réglages d'affichage sont
poussés à chaud sur l'overlay via `on_live_change` ; ceux de transcription ne
prennent effet qu'au prochain lancement — un bandeau le signale.

Le style suit la fenêtre principale (`benji.ui.style`) : dégradé de fond,
sections encadrées discrètes, contrôles thémés, bouton d'action en accent. Se
recharge au changement de thème système.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from PyQt6.QtCore import Qt
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
from benji.ui.style import FONT_UI, current_theme, install_theme_listener

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


# Famille système macOS (privée, préfixée « . ») : QFontComboBox ne sait pas
# l'afficher et retombe sur une entrée arbitraire de la liste. On la représente
# par « Helvetica Neue », la police native la plus proche réellement listée.
_SYSTEM_FONT_DISPLAY = "Helvetica Neue"


def _resolve_font(family: str) -> QFont:
    """QFont affichable dans le combo pour une famille de config donnée."""
    if not family or family.startswith("."):
        return QFont(_SYSTEM_FONT_DISPLAY)
    return QFont(family)


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
        self.setMinimumWidth(420)

        self._build_ui()
        install_theme_listener(self._apply_theme)
        self._apply_theme()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(16)

        # === Transcription (redémarrage requis) ===
        self._stt_box = QGroupBox("TRANSCRIPTION")
        stt_form = QFormLayout(self._stt_box)
        stt_form.setContentsMargins(16, 18, 16, 16)
        stt_form.setSpacing(12)
        stt_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

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

        self._hint = QLabel("Ces réglages prennent effet au prochain démarrage.")
        stt_form.addRow(self._hint)
        layout.addWidget(self._stt_box)

        # === Affichage (application immédiate) ===
        self._ui_box = QGroupBox("AFFICHAGE")
        ui_form = QFormLayout(self._ui_box)
        ui_form.setContentsMargins(16, 18, 16, 16)
        ui_form.setSpacing(12)
        ui_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._font = QFontComboBox()
        self._font.setCurrentFont(_resolve_font(self._ui.font_family))
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

        layout.addWidget(self._ui_box)
        layout.addStretch(1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._save_btn = self._buttons.button(QDialogButtonBox.StandardButton.Save)
        self._cancel_btn = self._buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self._save_btn.setText("Enregistrer")
        self._cancel_btn.setText("Annuler")
        self._save_btn.setObjectName("accent_btn")
        self._cancel_btn.setObjectName("ghost_btn")
        self._buttons.accepted.connect(self._save)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _apply_theme(self) -> None:
        t = current_theme()
        bg = t.window_background
        delta = 6 if t.is_dark else 5
        top = bg.lighter(100 + delta)
        bottom = bg.darker(100 + delta)
        label = t.label
        sec = t.secondary_label
        tert = t.tertiary_label
        accent = t.accent
        sep = t.separator
        field_bg = t.label_alpha(6 if t.is_dark else 4)
        field_border = t.label_alpha(14 if t.is_dark else 12)

        def rgba(c):
            return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"

        self.setStyleSheet(f"""
            QDialog {{
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgb({top.red()},{top.green()},{top.blue()}),
                    stop:1 rgb({bottom.red()},{bottom.green()},{bottom.blue()})
                );
            }}
            QGroupBox {{
                font-family: {FONT_UI};
                font-size: 10px;
                font-weight: 600;
                color: {rgba(tert)};
                border: 1px solid {rgba(sep)};
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 6px;
                background-color: {rgba(t.label_alpha(3))};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                top: 1px;
                padding: 0 4px;
                letter-spacing: 0.6px;
            }}
            QLabel {{
                font-family: {FONT_UI};
                font-size: 13px;
                color: {rgba(label)};
                background: transparent;
            }}
            QComboBox, QFontComboBox, QSpinBox {{
                font-family: {FONT_UI};
                font-size: 13px;
                color: {rgba(label)};
                background-color: {rgba(field_bg)};
                border: 1px solid {rgba(field_border)};
                border-radius: 6px;
                padding: 4px 8px;
                min-height: 22px;
            }}
            QComboBox:hover, QFontComboBox:hover, QSpinBox:hover {{
                border-color: {rgba(t.accent_alpha(45))};
            }}
            QComboBox::drop-down, QFontComboBox::drop-down {{ border: none; width: 18px; }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; }}
            QCheckBox {{
                font-family: {FONT_UI};
                font-size: 13px;
                color: {rgba(label)};
                spacing: 8px;
                background: transparent;
            }}
            QPushButton#accent_btn {{
                font-family: {FONT_UI};
                font-size: 13px;
                font-weight: 500;
                color: #ffffff;
                background-color: rgb({accent.red()},{accent.green()},{accent.blue()});
                border: none;
                padding: 7px 18px;
                border-radius: 6px;
            }}
            QPushButton#accent_btn:hover {{
                background-color: rgba({accent.red()},{accent.green()},{accent.blue()},220);
            }}
            QPushButton#ghost_btn {{
                font-family: {FONT_UI};
                font-size: 13px;
                font-weight: 500;
                color: {rgba(label)};
                background: transparent;
                border: 1px solid {rgba(field_border)};
                padding: 7px 16px;
                border-radius: 6px;
            }}
            QPushButton#ghost_btn:hover {{
                background-color: {rgba(t.label_alpha(8))};
            }}
        """)
        # Le bandeau d'info en couleur secondaire (le QSS QLabel ci-dessus cible
        # aussi ce label, on le repasse en tertiaire ici pour le distinguer).
        self._hint.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 11px; color: {rgba(sec)}; background: transparent;"
        )

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
