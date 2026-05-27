"""Onglet 'Résumés' : liste à gauche, preview markdown à droite."""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QFileSystemWatcher
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

log = logging.getLogger(__name__)

_SUMMARY_FILENAME = re.compile(r"summary_(\d{8})_(\d{6})\.md$")


def _default_dir() -> Path:
    return Path.home() / ".cache" / "benji" / "summaries"


class SummariesTab(QWidget):
    def __init__(self, summaries_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._dir = summaries_dir or _default_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._pending_text: str = ""
        self._build_ui()
        self._wire()
        self.reload()
        self._install_watcher()

    def _build_ui(self) -> None:
        self.list_widget = QListWidget()
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.setPlaceholderText("Cliquez sur un résumé pour le voir")

        self.copy_btn = QPushButton("Copier")
        self.reveal_btn = QPushButton("Révéler dans Finder")
        self.copy_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)

        right_top = QHBoxLayout()
        right_top.addWidget(self.copy_btn)
        right_top.addWidget(self.reveal_btn)
        right_top.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(right_top)
        right_layout.addWidget(self.preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.list_widget)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def _wire(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_selection)
        self.copy_btn.clicked.connect(self._copy_selected)
        self.reveal_btn.clicked.connect(self._reveal_selected)

    def _install_watcher(self) -> None:
        self._watcher = QFileSystemWatcher([str(self._dir)], self)
        self._watcher.directoryChanged.connect(lambda _: self.reload())

    def reload(self) -> None:
        prev_path = self._selected_path()
        files = sorted(
            self._dir.glob("summary_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        self.list_widget.clear()
        for p in files:
            item = QListWidgetItem(self._format_label(p))
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.list_widget.addItem(item)
        if prev_path:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == prev_path:
                    self.list_widget.setCurrentRow(i)
                    break

    def _format_label(self, p: Path) -> str:
        m = _SUMMARY_FILENAME.search(p.name)
        if m:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            head = dt.strftime("%d %b · %H:%M")
        else:
            head = p.stem
        snippet = self._first_line(p)
        return f"{head}\n{snippet}" if snippet else head

    @staticmethod
    def _first_line(p: Path) -> str:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    return (line[:60] + "…") if len(line) > 60 else line
        except Exception:
            pass
        return ""

    def _selected_path(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection(self) -> None:
        path = self._selected_path()
        # Pending placeholders store "__pending__:<id>" — pas un vrai fichier.
        is_real_file = path is not None and not path.startswith("__pending__:")
        self.copy_btn.setEnabled(is_real_file)
        self.reveal_btn.setEnabled(is_real_file)
        if not is_real_file:
            if path is None:
                self.preview.clear()
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            self.preview.setMarkdown(text)
        except Exception as e:
            self.preview.setPlainText(f"Erreur de lecture : {e}")

    def _copy_selected(self) -> None:
        path = self._selected_path()
        if not path or path.startswith("__pending__:"):
            return
        try:
            QGuiApplication.clipboard().setText(Path(path).read_text(encoding="utf-8"))
        except Exception:
            log.exception("Copy failed")

    def _reveal_selected(self) -> None:
        path = self._selected_path()
        if not path or path.startswith("__pending__:"):
            return
        try:
            subprocess.run(["open", "-R", path], check=False)
        except Exception:
            log.exception("Reveal failed")

    # --- API pour le SummaryWorker en cours ---

    def begin_pending(self, summary_id: str) -> None:
        item = QListWidgetItem(f"🟠 En cours…\n{datetime.now().strftime('%H:%M:%S')}")
        item.setData(Qt.ItemDataRole.UserRole, f"__pending__:{summary_id}")
        self.list_widget.insertItem(0, item)
        self.list_widget.setCurrentRow(0)
        self.preview.clear()
        self._pending_text = ""

    def append_chunk(self, summary_id: str, chunk: str) -> None:
        item = self._find_pending(summary_id)
        if item is None:
            return
        self._pending_text += chunk
        self.preview.setMarkdown(self._pending_text)

    def finalize_pending(self, summary_id: str, path) -> None:
        item = self._find_pending(summary_id)
        if item is not None:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        self.reload()
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == str(path):
                self.list_widget.setCurrentRow(i)
                break

    def fail_pending(self, summary_id: str, error: str) -> None:
        item = self._find_pending(summary_id)
        if item is None:
            return
        item.setText(f"🔴 Échec — {error[:80]}")
        item.setData(Qt.ItemDataRole.UserRole, None)

    def _find_pending(self, summary_id: str):
        marker = f"__pending__:{summary_id}"
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == marker:
                return it
        return None
