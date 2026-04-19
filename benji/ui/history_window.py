import threading
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QLabel,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

from benji.history import TranscriptionHistory
from benji.stats import SessionStats


class HistoryWindow(QWidget):
    _summary_ready = pyqtSignal(str, str)  # (summary_text, file_path)
    _summary_error = pyqtSignal(str)

    def __init__(self, session_start: datetime = None, stats: SessionStats | None = None):
        super().__init__()
        self.history = TranscriptionHistory()
        self.session_start = session_start or datetime.now()
        self.stats = stats
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
        self.summarize_btn = QPushButton("Résumer la session")
        self.summarize_btn.clicked.connect(self._start_summarize)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)

        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(clear_btn)
        button_layout.addWidget(self.summarize_btn)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)

        # Stats footer (updated every 2s)
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        layout.addWidget(self.stats_label)

        self.setLayout(layout)

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(2000)
        self._refresh_stats()

        self._summary_ready.connect(self._on_summary_ready)
        self._summary_error.connect(self._on_summary_error)

        self.load_history()

    def _start_summarize(self):
        self.summarize_btn.setEnabled(False)
        self.summarize_btn.setText("Génération en cours…")
        threading.Thread(target=self._run_summarize, daemon=True).start()

    def _run_summarize(self):
        from benji.llm.summarizer import summarize, save_summary
        entries = self.history.get_since(self.session_start)
        if not entries:
            self._summary_error.emit("Aucune transcription dans cette session.")
            return
        summary = summarize(entries)
        if not summary:
            self._summary_error.emit("Impossible de générer un résumé.")
            return
        path = save_summary(summary)
        self._summary_ready.emit(summary, str(path))

    def _on_summary_ready(self, summary: str, path: str):
        self.text_edit.append(f"\n{'─' * 60}")
        self.text_edit.append(f"Résumé de session ({datetime.now().strftime('%H:%M')})\n")
        self.text_edit.append(summary)
        self.text_edit.append(f"\n💾 Sauvegardé : {path}")
        self.summarize_btn.setText("Résumer la session")
        self.summarize_btn.setEnabled(True)

    def _on_summary_error(self, message: str):
        self.text_edit.append(f"\n[Résumé] {message}")
        self.summarize_btn.setText("Résumer la session")
        self.summarize_btn.setEnabled(True)

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

    def _refresh_stats(self):
        if self.stats is None:
            self.stats_label.setText("")
            return
        self.stats_label.setText(self.stats.format_footer())
