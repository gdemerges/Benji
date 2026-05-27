"""Item résumé en cours de génération — spinner pill fin."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from benji.ui.style import current_theme, FONT_UI


class PendingItem(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("Génération du résumé…")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)

        self.apply_theme()

    def apply_theme(self) -> None:
        t = current_theme()
        bg = t.accent_alpha(10)
        self.setStyleSheet(f"""
            PendingItem {{
                background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});
                border-radius: 6px;
            }}
        """)
        self.label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 12px; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
        track = t.label_alpha(8)
        accent = t.accent
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba({track.red()},{track.green()},{track.blue()},{track.alpha()});
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: rgb({accent.red()},{accent.green()},{accent.blue()});
                border-radius: 1px;
            }}
        """)

    def set_failed(self, error: str) -> None:
        t = current_theme()
        red = t.live_red
        self.label.setText(f"Échec — {error[:80]}")
        self.bar.setVisible(False)
        self.setStyleSheet(f"""
            PendingItem {{
                background-color: rgba({red.red()},{red.green()},{red.blue()},25);
                border-radius: 6px;
            }}
        """)
        self.label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 12px; "
            f"color: rgb({red.red()},{red.green()},{red.blue()}); "
            "background: transparent;"
        )
