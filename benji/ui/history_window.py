from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from benji.history import TranscriptionHistory


class HistoryWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.history = TranscriptionHistory()
        self.setWindowTitle("Transcription History")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(600, 400)

        # Layout
        layout = QVBoxLayout()

        # Text area
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("monospace", 10))
        layout.addWidget(self.text_edit)

        # Buttons
        button_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_history)
        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self.clear_history)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(clear_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        self.setLayout(layout)
        self.load_history()

    def load_history(self):
        entries = self.history.get_recent(100)
        if not entries:
            self.text_edit.setPlainText("No transcriptions yet.")
            return

        text = ""
        for entry in entries:
            ts = datetime.fromisoformat(entry["timestamp"])
            time_str = ts.strftime("%Y-%m-%d %H:%M:%S")
            text += f"[{time_str}] {entry['text']}\n\n"
        self.text_edit.setPlainText(text.strip())
        # Move cursor to end
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)

    def clear_history(self):
        self.history.clear()
        self.text_edit.setPlainText("History cleared.")
