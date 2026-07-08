"""Onglet 'Résumés' : liste groupée par jour + preview markdown stylée."""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QSize, Qt
from PyQt6.QtGui import QGuiApplication, QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from benji.ui.style import FONT_DISPLAY, FONT_MONO, FONT_UI, current_theme
from benji.ui.widgets.icons import clipboard_icon, folder_arrow_icon
from benji.ui.widgets.pending_item import PendingItem
from benji.ui.widgets.summary_item import SummaryItem

log = logging.getLogger(__name__)

_SUMMARY_FILENAME = re.compile(r"summary_(\d{8})_(\d{6})\.md$")
_HEADER_PREFIX = "__header__:"
_PENDING_PREFIX = "__pending__:"


def _default_dir() -> Path:
    return Path.home() / ".cache" / "benji" / "summaries"


class SummariesTab(QWidget):
    def __init__(self, summaries_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._dir = summaries_dir or _default_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._pending_text: str = ""
        self._pending_items: dict[str, QListWidgetItem] = {}
        self._build_ui()
        self._wire()
        self.reload()
        self._install_watcher()
        self.apply_theme()

    def _build_ui(self) -> None:
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QListWidget.Shape.NoFrame)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.setSpacing(2)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.preview.setPlaceholderText("Cliquez sur un résumé pour le voir")

        self.copy_btn = QPushButton("Copier")
        self.reveal_btn = QPushButton("Révéler dans Finder")
        self.copy_btn.setObjectName("toolbar_btn")
        self.reveal_btn.setObjectName("toolbar_btn")
        self.copy_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)

        right_top = QHBoxLayout()
        right_top.setContentsMargins(12, 8, 12, 4)
        right_top.addWidget(self.copy_btn)
        right_top.addWidget(self.reveal_btn)
        right_top.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(right_top)
        right_layout.addWidget(self.preview, 1)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(self.list_widget)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.addWidget(self.splitter)

    def _wire(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_selection)
        self.copy_btn.clicked.connect(self._copy_selected)
        self.reveal_btn.clicked.connect(self._reveal_selected)

    def _install_watcher(self) -> None:
        self._watcher = QFileSystemWatcher([str(self._dir)], self)
        self._watcher.directoryChanged.connect(lambda _: self.reload())

    def apply_theme(self) -> None:
        t = current_theme()
        sel_bg = t.accent_alpha(18)
        hover_bg = t.label_alpha(5)
        separator = t.separator
        self.setStyleSheet(f"""
            SummariesTab, QSplitter, QTextBrowser, QListWidget {{ background: transparent; }}
            QSplitter::handle {{ background-color: rgba({separator.red()},{separator.green()},{separator.blue()},{separator.alpha()}); }}
            QListWidget {{ border: none; outline: none; padding: 8px 6px; }}
            QListWidget::item {{
                border-radius: 6px;
                padding: 0px;
                margin: 1px 4px;
            }}
            QListWidget::item:selected {{
                background-color: rgba({sel_bg.red()},{sel_bg.green()},{sel_bg.blue()},{sel_bg.alpha()});
            }}
            QListWidget::item:hover:!selected {{
                background-color: rgba({hover_bg.red()},{hover_bg.green()},{hover_bg.blue()},{hover_bg.alpha()});
            }}
            QPushButton#toolbar_btn {{
                font-family: {FONT_UI};
                font-size: 12px;
                color: rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()});
                background: transparent;
                border: none;
                padding: 5px 10px;
                border-radius: 5px;
            }}
            QPushButton#toolbar_btn:hover {{
                background-color: rgba({hover_bg.red()},{hover_bg.green()},{hover_bg.blue()},{hover_bg.alpha()});
            }}
            QPushButton#toolbar_btn:disabled {{
                color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()});
            }}
        """)
        label_hex = f"#{t.label.red():02x}{t.label.green():02x}{t.label.blue():02x}"
        self.copy_btn.setIcon(clipboard_icon(label_hex))
        self.reveal_btn.setIcon(folder_arrow_icon(label_hex))
        self._apply_preview_css()
        self._refresh_item_widget_themes()

    def _apply_preview_css(self) -> None:
        t = current_theme()
        label_rgba = f"rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()})"
        sec_rgba = f"rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()})"
        code_bg = t.label_alpha(8)
        code_rgba = f"rgba({code_bg.red()},{code_bg.green()},{code_bg.blue()},{code_bg.alpha()})"
        accent_rgba = f"rgb({t.accent.red()},{t.accent.green()},{t.accent.blue()})"
        css = f"""
            body {{ font-family: {FONT_UI}; font-size: 14px; line-height: 1.6; color: {label_rgba}; padding: 24px 28px; }}
            h1 {{ font-family: {FONT_DISPLAY}; font-size: 22px; font-weight: 600; margin: 0 0 16px 0; }}
            h2 {{ font-size: 17px; font-weight: 600; margin: 20px 0 10px 0; }}
            h3 {{ font-size: 15px; font-weight: 600; margin: 16px 0 8px 0; }}
            p {{ margin: 0 0 12px 0; }}
            code {{ font-family: {FONT_MONO}; font-size: 13px; background-color: {code_rgba}; padding: 1px 5px; border-radius: 3px; }}
            pre {{ background-color: {code_rgba}; padding: 10px 14px; border-radius: 6px; }}
            pre code {{ background: transparent; padding: 0; }}
            blockquote {{ border-left: 3px solid {accent_rgba}; padding-left: 12px; color: {sec_rgba}; margin: 12px 0; }}
            ul, ol {{ margin: 0 0 12px 18px; padding: 0; }}
            li {{ margin-bottom: 4px; }}
            a {{ color: {accent_rgba}; text-decoration: none; }}
        """
        self.preview.document().setDefaultStyleSheet(css)
        path = self._selected_path()
        if path and not path.startswith(_PENDING_PREFIX) and not path.startswith(_HEADER_PREFIX):
            try:
                self._render_markdown(Path(path).read_text(encoding="utf-8"))
            except Exception:
                pass

    def _refresh_item_widget_themes(self) -> None:
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w is not None and hasattr(w, "apply_theme"):
                w.apply_theme()

    def reload(self) -> None:
        prev_path = self._selected_path()
        files = sorted(
            self._dir.glob("summary_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        self.list_widget.clear()

        current_group: str | None = None
        for p in files:
            dt = self._dt_from_path(p)
            group = self._group_label(dt.date())
            if group != current_group:
                self._add_header(group)
                current_group = group
            self._add_summary_item(p, dt)

        if prev_path:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == prev_path:
                    self.list_widget.setCurrentRow(i)
                    break

    def _add_header(self, label: str) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, f"{_HEADER_PREFIX}{label}")
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(0, 28))
        t = current_theme()
        header = QLabel(label.upper())
        header.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 0.6px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "padding: 12px 14px 4px 14px; background: transparent;"
        )
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, header)

    def _add_summary_item(self, path: Path, dt: datetime) -> None:
        snippet = self._first_line(path)
        widget = SummaryItem(dt, snippet)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setSizeHint(widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)

    @staticmethod
    def _dt_from_path(p: Path) -> datetime:
        m = _SUMMARY_FILENAME.search(p.name)
        if m:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        return datetime.fromtimestamp(p.stat().st_mtime)

    @staticmethod
    def _group_label(d: date) -> str:
        today = date.today()
        if d == today:
            return "Aujourd'hui"
        if d == today - timedelta(days=1):
            return "Hier"
        if (today - d).days < 7:
            return d.strftime("%A")
        return d.strftime("%d %B %Y")

    @staticmethod
    def _first_line(p: Path) -> str:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    return (line[:70] + "…") if len(line) > 70 else line
        except Exception:
            pass
        return ""

    # Marges (haut, bas) en px injectées par niveau de titre. QTextBrowser.setMarkdown
    # ignore les marges CSS des titres — on les pose donc directement sur les
    # QTextBlockFormat après rendu, sinon H2/H3 collent au texte précédent.
    _HEADING_MARGINS = {1: (2, 12), 2: (22, 8), 3: (16, 6)}

    def _render_markdown(self, text: str) -> None:
        """setMarkdown + espacement des titres (contourne l'ignorance des marges CSS)."""
        self.preview.setMarkdown(text)
        doc = self.preview.document()
        block = doc.begin()
        while block.isValid():
            level = block.blockFormat().headingLevel()
            if level in self._HEADING_MARGINS:
                top, bottom = self._HEADING_MARGINS[level]
                fmt = block.blockFormat()
                fmt.setTopMargin(top)
                fmt.setBottomMargin(bottom)
                cursor = QTextCursor(block)
                cursor.setBlockFormat(fmt)
            block = block.next()

    def _selected_path(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection(self) -> None:
        path = self._selected_path()
        is_real_file = (
            path is not None
            and not path.startswith(_PENDING_PREFIX)
            and not path.startswith(_HEADER_PREFIX)
        )
        self.copy_btn.setEnabled(is_real_file)
        self.reveal_btn.setEnabled(is_real_file)
        if not is_real_file:
            if path is None:
                self.preview.clear()
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            self._render_markdown(text)
        except Exception as e:
            self.preview.setPlainText(f"Erreur de lecture : {e}")

    def _copy_selected(self) -> None:
        path = self._selected_path()
        if not path or path.startswith(_PENDING_PREFIX) or path.startswith(_HEADER_PREFIX):
            return
        try:
            QGuiApplication.clipboard().setText(Path(path).read_text(encoding="utf-8"))
        except Exception:
            log.exception("Copy failed")

    def _reveal_selected(self) -> None:
        path = self._selected_path()
        if not path or path.startswith(_PENDING_PREFIX) or path.startswith(_HEADER_PREFIX):
            return
        try:
            subprocess.run(["open", "-R", path], check=False)
        except Exception:
            log.exception("Reveal failed")

    # --- API pour le SummaryWorker ---

    def begin_pending(self, summary_id: str) -> None:
        widget = PendingItem()
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, f"{_PENDING_PREFIX}{summary_id}")
        item.setSizeHint(widget.sizeHint())
        insert_at = 1 if (self.list_widget.count() > 0 and
                          (self.list_widget.item(0).data(Qt.ItemDataRole.UserRole) or "").startswith(_HEADER_PREFIX)) else 0
        self.list_widget.insertItem(insert_at, item)
        self.list_widget.setItemWidget(item, widget)
        self._pending_items[summary_id] = item
        self.list_widget.setCurrentRow(insert_at)
        self.preview.clear()
        self._pending_text = ""

    def append_chunk(self, summary_id: str, chunk: str) -> None:
        if summary_id not in self._pending_items:
            return
        self._pending_text += chunk
        self._render_markdown(self._pending_text)

    def finalize_pending(self, summary_id: str, path) -> None:
        item = self._pending_items.pop(summary_id, None)
        if item is not None:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        self.reload()
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == str(path):
                self.list_widget.setCurrentRow(i)
                break

    def fail_pending(self, summary_id: str, error: str) -> None:
        item = self._pending_items.get(summary_id)
        if item is None:
            return
        widget = self.list_widget.itemWidget(item)
        if isinstance(widget, PendingItem):
            widget.set_failed(error)
        item.setData(Qt.ItemDataRole.UserRole, None)
        self._pending_items.pop(summary_id, None)
