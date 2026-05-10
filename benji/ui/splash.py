"""Splash window shown while the Whisper model loads."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class SplashWindow(QWidget):
    _status_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Benji")
        self.setWindowFlags(Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(360, 140)

        title = QLabel("Benji")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(22)
        title_font.setBold(True)
        title.setFont(title_font)

        self._status = QLabel("Initialisation…")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addWidget(self._status)
        self.setLayout(layout)

        self._status_signal.connect(self._status.setText)

    def set_status(self, text: str) -> None:
        """Thread-safe status update."""
        self._status_signal.emit(text)
