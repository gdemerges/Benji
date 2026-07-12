import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from benji import export
from benji.history import TranscriptionHistory
from benji.stats import SessionStats
from benji.ui.style import (
    FONT_MONO,
    current_theme,
    install_theme_listener,
    panel_background_qss,
    primary_button_qss,
    secondary_button_qss,
    text_panel_qss,
)

_EXPORT_FORMATS = [
    ("Texte (.txt)", "txt", "Fichier texte (*.txt)"),
    ("Markdown (.md)", "md", "Markdown (*.md)"),
    ("Sous-titres (.srt)", "srt", "SubRip (*.srt)"),
]


class HistoryWindow(QWidget):
    _summary_ready = pyqtSignal(str, str)  # (summary_text, file_path)
    _summary_error = pyqtSignal(str)

    def __init__(self, session_start: datetime = None, stats: SessionStats | None = None):
        super().__init__()
        self.history = TranscriptionHistory()
        self.session_start = session_start or datetime.now()
        self.stats = stats
        self._entries: list[dict] = []
        self._speaker_names: dict[str, str] = {}
        self.setObjectName("HistoryWindow")
        self.setWindowTitle("Historique")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(640, 460)

        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(12)

        # Text area
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont(FONT_MONO, 12))
        layout.addWidget(self.text_edit)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        self.refresh_btn = QPushButton("Actualiser")
        self.refresh_btn.clicked.connect(self.load_history)
        self.clear_btn = QPushButton("Effacer")
        self.clear_btn.clicked.connect(self.clear_history)
        self.copy_btn = QPushButton("Copier")
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        self.export_btn = QPushButton("Exporter…")
        self.export_btn.clicked.connect(self._open_export_menu)
        self.speakers_btn = QPushButton("Locuteurs…")
        self.speakers_btn.clicked.connect(self._rename_speakers)
        self.summarize_btn = QPushButton("Résumer la session")
        self.summarize_btn.clicked.connect(self._start_summarize)
        self.close_btn = QPushButton("Fermer")
        self.close_btn.clicked.connect(self.close)

        # Boutons secondaires (discrets) et principal (accent).
        self._secondary_buttons = [
            self.refresh_btn,
            self.clear_btn,
            self.copy_btn,
            self.export_btn,
            self.speakers_btn,
            self.close_btn,
        ]
        for btn in (self.refresh_btn, self.clear_btn, self.copy_btn,
                    self.export_btn, self.speakers_btn):
            button_layout.addWidget(btn)
        button_layout.addWidget(self.summarize_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)
        layout.addLayout(button_layout)

        # Stats footer (updated every 2s)
        self.stats_label = QLabel("")
        layout.addWidget(self.stats_label)

        self.setLayout(layout)

        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._refresh_stats)
        self._stats_timer.start(2000)
        self._refresh_stats()

        self._summary_ready.connect(self._on_summary_ready)
        self._summary_error.connect(self._on_summary_error)

        install_theme_listener(self._apply_theme)
        self._apply_theme()

        self.load_history()

    def _apply_theme(self) -> None:
        t = current_theme()
        self.setStyleSheet(
            panel_background_qss(t, "#HistoryWindow") + text_panel_qss(t)
        )
        for btn in self._secondary_buttons:
            btn.setStyleSheet(secondary_button_qss(t))
        self.summarize_btn.setStyleSheet(primary_button_qss(t))
        self.stats_label.setStyleSheet(
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},"
            f"{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "font-size: 11px; padding: 2px 4px;"
        )

    def _start_summarize(self):
        self.summarize_btn.setEnabled(False)
        self.summarize_btn.setText("Génération en cours…")
        threading.Thread(target=self._run_summarize, daemon=True).start()

    def _run_summarize(self):
        from benji.llm.summarizer import save_summary, summarize
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
        # get_recent renvoie le plus récent en premier ; on garde l'ordre
        # chronologique pour l'affichage et l'export (les modules d'export
        # retrient de toute façon).
        self._entries = list(reversed(self.history.get_recent(100)))
        self._refresh_export_enabled()
        if not self._entries:
            self.text_edit.setPlainText("No transcriptions yet.")
            return

        self.text_edit.setPlainText(export.to_txt(self._entries, self._speaker_names).strip())
        # Move cursor to end
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)

    def _refresh_export_enabled(self):
        has_entries = bool(self._entries)
        self.copy_btn.setEnabled(has_entries)
        self.export_btn.setEnabled(has_entries)
        self.speakers_btn.setEnabled(bool(export.distinct_speakers(self._entries)))

    def _copy_to_clipboard(self):
        if not self._entries:
            return
        QGuiApplication.clipboard().setText(export.to_txt(self._entries, self._speaker_names))

    def _open_export_menu(self):
        if not self._entries:
            return
        menu = QMenu(self)
        for label, fmt, file_filter in _EXPORT_FORMATS:
            menu.addAction(label, lambda f=fmt, ff=file_filter: self._export(f, ff))
        menu.exec(self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft()))

    def _export(self, fmt: str, file_filter: str):
        default_name = f"benji-{datetime.now().strftime('%Y%m%d-%H%M%S')}.{fmt}"
        default_path = str(Path.home() / "Downloads" / default_name)
        path, _ = QFileDialog.getSaveFileName(self, "Exporter la transcription", default_path, file_filter)
        if not path:
            return
        content = export.render(self._entries, fmt, self._speaker_names)
        try:
            Path(path).write_text(content, encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Benji", f"Export impossible : {e}")

    def _rename_speakers(self):
        labels = export.distinct_speakers(self._entries)
        if not labels:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Renommer les locuteurs")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        edits: dict[str, QLineEdit] = {}
        for label in labels:
            edit = QLineEdit(self._speaker_names.get(label, ""))
            edit.setPlaceholderText(label)
            edits[label] = edit
            form.addRow(f"Locuteur {label} :", edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        for label, edit in edits.items():
            name = edit.text().strip()
            if name:
                self._speaker_names[label] = name
            else:
                self._speaker_names.pop(label, None)
        self.load_history()  # ré-affiche avec les nouveaux noms

    def clear_history(self):
        self.history.clear()
        self._entries = []
        self._speaker_names = {}
        self._refresh_export_enabled()
        self.text_edit.setPlainText("History cleared.")

    def _refresh_stats(self):
        if self.stats is None:
            self.stats_label.setText("")
            return
        self.stats_label.setText(self.stats.format_footer())
