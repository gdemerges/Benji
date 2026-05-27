"""Palette adaptive, helpers QSS et vibrancy macOS pour la fenêtre principale."""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

log = logging.getLogger(__name__)


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


# Font stacks
FONT_UI = '"-apple-system", "SF Pro Text", system-ui, sans-serif'
FONT_DISPLAY = '"-apple-system", "SF Pro Display", "SF Pro Text", system-ui, sans-serif'
FONT_MONO = '"SF Mono", Menlo, monospace'


def apply_window_vibrancy(window: QWidget) -> None:
    """macOS : NSVisualEffectView material underWindowBackground. No-op ailleurs."""
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import (
            NSColor,
            NSVisualEffectView,
            NSVisualEffectMaterialUnderWindowBackground,
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectStateActive,
        )
        import objc

        view_ptr = int(window.winId())
        ns_view = objc.objc_object(c_void_p=view_ptr)
        ns_window = ns_view.window()
        content = ns_window.contentView()

        effect = NSVisualEffectView.alloc().initWithFrame_(content.bounds())
        effect.setAutoresizingMask_(18)  # width-sizable | height-sizable
        effect.setMaterial_(NSVisualEffectMaterialUnderWindowBackground)
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        content.addSubview_positioned_relativeTo_(effect, -1, None)  # below all

        ns_window.setOpaque_(False)
        ns_window.setBackgroundColor_(NSColor.clearColor())
        log.info("macOS vibrancy applied")
    except Exception as e:
        log.warning("vibrancy failed: %s", e)
