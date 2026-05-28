"""Pill statut : dot pulsant + label + timer session."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtProperty,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from benji.ui.style import FONT_MONO, FONT_UI, current_theme


class _PulseDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = QColor(150, 150, 150)
        self._opacity = 1.0
        self._anim = QPropertyAnimation(self, b"opacity_prop")
        self._anim.setDuration(1200)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.35)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def set_pulsing(self, on: bool) -> None:
        if on:
            self._anim.start()
        else:
            self._anim.stop()
            self._opacity = 1.0
            self.update()

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, v: float) -> None:
        self._opacity = v
        self.update()

    opacity_prop = pyqtProperty(float, fget=_get_opacity, fset=_set_opacity)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(self._opacity)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 8, 8)


class StatusPill(QWidget):
    def __init__(self, session_start: datetime, parent=None):
        super().__init__(parent)
        self._session_start = session_start
        self._speaking = False

        self.dot = _PulseDot(self)
        self.status_label = QLabel("En attente")
        self.sep_label = QLabel(" · ")
        self.timer_label = QLabel("00:00")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 12, 4)
        layout.setSpacing(6)
        layout.addWidget(self.dot)
        layout.addSpacing(2)
        layout.addWidget(self.status_label)
        layout.addWidget(self.sep_label)
        layout.addWidget(self.timer_label)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        self.apply_theme()

    def apply_theme(self) -> None:
        t = current_theme()
        bg = t.label_alpha(6) if t.is_dark else t.label_alpha(5)
        self.setStyleSheet(f"""
            StatusPill {{
                background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});
                border-radius: 11px;
            }}
            QLabel {{
                font-family: {FONT_UI};
                font-size: 12px;
                color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()});
                background: transparent;
            }}
        """)
        self.timer_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 12px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent;"
        )
        self._refresh_dot_color()

    def set_speaking(self, speaking: bool) -> None:
        if speaking == self._speaking:
            return
        self._speaking = speaking
        self.status_label.setText("En écoute" if speaking else "En attente")
        self._refresh_dot_color()
        self.dot.set_pulsing(speaking)

    def _refresh_dot_color(self) -> None:
        t = current_theme()
        self.dot.set_color(t.live_red if self._speaking else t.tertiary_label)

    def _tick(self) -> None:
        delta: timedelta = datetime.now() - self._session_start
        total = int(delta.total_seconds())
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        self.timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")
