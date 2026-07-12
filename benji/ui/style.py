"""Palette adaptive, helpers QSS et vibrancy macOS pour la fenêtre principale."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

from benji.config import IS_MACOS

log = logging.getLogger(__name__)


def vibrancy_enabled() -> bool:
    """Vibrancy macOS native : opt-in via BENJI_VIBRANCY (1/true/yes).

    Désactivée par défaut — le swap de contentView NSVisualEffectView doit être
    validé en live (grab() ne capture pas la composition native), et le fallback
    dégradé plat reste sûr sur toutes les versions de Qt."""
    return os.environ.get("BENJI_VIBRANCY", "").lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Theme:
    is_dark: bool
    label: QColor
    secondary_label: QColor
    tertiary_label: QColor
    quaternary_label: QColor
    accent: QColor
    live_red: QColor
    window_background: QColor
    separator: QColor

    def accent_alpha(self, pct: int) -> QColor:
        c = QColor(self.accent)
        c.setAlpha(int(255 * pct / 100))
        return c

    def label_alpha(self, pct: int) -> QColor:
        c = QColor(self.label)
        c.setAlpha(int(255 * pct / 100))
        return c

    @staticmethod
    def color_alpha(color: QColor, pct: int) -> QColor:
        c = QColor(color)
        c.setAlpha(int(255 * pct / 100))
        return c


def _is_dark() -> bool:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        return False


def current_theme() -> Theme:
    dark = _is_dark()
    if dark:
        return Theme(
            is_dark=True,
            label=QColor(255, 255, 255, 230),
            secondary_label=QColor(255, 255, 255, 153),
            tertiary_label=QColor(255, 255, 255, 102),
            quaternary_label=QColor(255, 255, 255, 51),
            accent=QApplication.palette().color(QPalette.ColorRole.Highlight),
            live_red=QColor("#FF453A"),
            window_background=QColor(30, 30, 30),
            separator=QColor(255, 255, 255, 38),
        )
    return Theme(
        is_dark=False,
        label=QColor(0, 0, 0, 217),
        secondary_label=QColor(0, 0, 0, 153),
        tertiary_label=QColor(0, 0, 0, 102),
        quaternary_label=QColor(0, 0, 0, 38),
        accent=QApplication.palette().color(QPalette.ColorRole.Highlight),
        live_red=QColor("#FF3B30"),
        window_background=QColor(246, 246, 246),
        separator=QColor(0, 0, 0, 25),
    )


def install_theme_listener(callback: Callable[[], None]) -> None:
    """Appelle `callback` chaque fois que le système bascule light/dark."""
    QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: callback())


# Speaker colors: a fixed, legible-on-both-themes palette. A label maps to a
# stable index so the same speaker always keeps the same color across the
# overlay and the chat-log.
_SPEAKER_PALETTE = [
    QColor("#0A84FF"),  # blue
    QColor("#FF375F"),  # pink
    QColor("#30D158"),  # green
    QColor("#FF9F0A"),  # orange
    QColor("#BF5AF2"),  # purple
    QColor("#40C8E0"),  # teal
    QColor("#FFD60A"),  # yellow
    QColor("#5E5CE6"),  # indigo
]


def speaker_color(label: str) -> QColor:
    """Stable, distinct color for a speaker label (e.g. 'A', 'B', 'S26')."""
    key = sum(ord(c) for c in label) if label else 0
    return QColor(_SPEAKER_PALETTE[key % len(_SPEAKER_PALETTE)])


# Font stacks
FONT_UI = '"-apple-system", "SF Pro Text", system-ui, sans-serif'
FONT_DISPLAY = '"-apple-system", "SF Pro Display", "SF Pro Text", system-ui, sans-serif'
FONT_MONO = '"SF Mono", Menlo, monospace'


def _rgba(color: QColor) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


def _rgb(color: QColor) -> str:
    return f"rgb({color.red()},{color.green()},{color.blue()})"


# --- QSS helpers partagés (source de vérité pour le look des fenêtres) --------
# Utilisés par les fenêtres héritées (history / live summary) pour rester
# cohérentes avec `main_window`, sans dupliquer les couleurs en dur.


def panel_background_qss(theme: Theme, selector: str = "QWidget") -> str:
    """Dégradé de fond vertical subtil, identique à la fenêtre principale."""
    bg = theme.window_background
    delta = 6 if theme.is_dark else 5
    top = bg.lighter(100 + delta)
    bottom = bg.darker(100 + delta)
    return f"""
    {selector} {{
        background-color: qlineargradient(
            x1:0, y1:0, x2:0, y2:1,
            stop:0 {_rgb(top)}, stop:1 {_rgb(bottom)}
        );
    }}"""


def text_panel_qss(theme: Theme) -> str:
    """QTextEdit en lecture : fond carte adaptive, texte label, coins arrondis."""
    card = theme.label_alpha(4)
    return f"""
    QTextEdit {{
        font-family: {FONT_MONO};
        font-size: 12px;
        color: {_rgba(theme.label)};
        background-color: {_rgba(card)};
        border: 1px solid {_rgba(theme.separator)};
        border-radius: 8px;
        padding: 10px;
        selection-background-color: {_rgba(theme.accent_alpha(40))};
        selection-color: {_rgba(theme.label)};
    }}"""


def primary_button_qss(theme: Theme) -> str:
    """Bouton d'action principal : rempli à la couleur d'accentuation."""
    accent = theme.accent
    return f"""
    QPushButton {{
        font-family: {FONT_UI};
        font-size: 12px;
        font-weight: 500;
        color: #ffffff;
        background-color: {_rgb(accent)};
        border: none;
        padding: 6px 14px;
        border-radius: 6px;
    }}
    QPushButton:hover {{ background-color: {_rgba(theme.accent_alpha(86))}; }}
    QPushButton:disabled {{
        background-color: {_rgba(theme.accent_alpha(35))};
        color: rgba(255,255,255,160);
    }}"""


def secondary_button_qss(theme: Theme) -> str:
    """Bouton secondaire : rempli discret, teinte label, hover plus marqué."""
    label = theme.label
    fill = theme.label_alpha(7)
    hover = theme.label_alpha(13)
    return f"""
    QPushButton {{
        font-family: {FONT_UI};
        font-size: 12px;
        font-weight: 500;
        color: {_rgba(label)};
        background-color: {_rgba(fill)};
        border: none;
        padding: 6px 12px;
        border-radius: 6px;
    }}
    QPushButton:hover {{ background-color: {_rgba(hover)}; }}
    QPushButton:disabled {{ color: {_rgba(theme.tertiary_label)}; background-color: {_rgba(theme.label_alpha(4))}; }}"""


def apply_window_vibrancy(window: QWidget) -> bool:
    """macOS vibrancy via NSVisualEffectView en remplaçant la contentView.

    Pattern "wrap" : la contentView Qt de la NSWindow est remplacée par un
    NSVisualEffectView (flou behind-window), l'ancienne vue Qt étant rattachée
    comme subview redimensionnable. Le fond Qt doit être transparent pour laisser
    voir le flou (cf. `_apply_theme` qui teste `_vibrancy_active`).

    Renvoie True si le swap a réussi. No-op + False si désactivé (BENJI_VIBRANCY),
    hors macOS, ou si AppKit échoue — l'appelant retombe alors sur le dégradé plat.
    """
    if not IS_MACOS or not vibrancy_enabled():
        return False
    try:
        import objc
        from AppKit import (
            NSViewHeightSizable,
            NSViewWidthSizable,
            NSVisualEffectView,
        )

        nsview = objc.objc_object(c_void_p=int(window.winId()))
        nswindow = nsview.window()
        if nswindow is None:
            return False

        effect = NSVisualEffectView.alloc().init()
        effect.setFrame_(nsview.bounds())
        effect.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        # BlendingModeBehindWindow=0, StateActive=1, Material UnderWindowBackground=21
        effect.setBlendingMode_(0)
        effect.setState_(1)
        try:
            effect.setMaterial_(21)
        except Exception:
            pass  # matériau indispo sur cette version : garde le défaut

        content = nswindow.contentView()
        nswindow.setContentView_(effect)
        effect.addSubview_(content)
        return True
    except Exception as e:
        log.warning("Vibrancy indisponible, fallback flat : %s", e)
        return False
