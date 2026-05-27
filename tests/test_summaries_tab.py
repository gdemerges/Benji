from pathlib import Path

import pytest

from benji.ui.summaries_tab import SummariesTab


def _write_summary(dir_path: Path, name: str, content: str) -> Path:
    p = dir_path / name
    p.write_text(content)
    return p


def test_loads_existing_summaries(qtbot, tmp_path):
    _write_summary(tmp_path, "summary_20260527_140000.md", "# Titre A\n\nCorps A")
    _write_summary(tmp_path, "summary_20260527_153000.md", "# Titre B\n\nCorps B")

    tab = SummariesTab(summaries_dir=tmp_path)
    qtbot.addWidget(tab)

    assert tab.list_widget.count() == 2
    # Le plus récent en haut (desc par mtime)
    top_item = tab.list_widget.item(0)
    assert "20260527_153000" in top_item.data(0x0100)  # Qt.ItemDataRole.UserRole = 0x0100


def test_selecting_item_renders_preview(qtbot, tmp_path):
    p = _write_summary(tmp_path, "summary_20260527_140000.md", "# Titre\n\nCorps texte")
    tab = SummariesTab(summaries_dir=tmp_path)
    qtbot.addWidget(tab)

    tab.list_widget.setCurrentRow(0)
    qtbot.wait(50)

    # toMarkdown sur QTextBrowser ne renvoie pas exactement l'input à cause du rendu HTML.
    # On vérifie que la source brute correspond au contenu du fichier.
    assert "Titre" in tab.preview.toPlainText()
    assert "Corps texte" in tab.preview.toPlainText()


def test_filewatcher_picks_up_new_file(qtbot, tmp_path):
    tab = SummariesTab(summaries_dir=tmp_path)
    qtbot.addWidget(tab)
    assert tab.list_widget.count() == 0

    _write_summary(tmp_path, "summary_20260527_140000.md", "# Nouveau\n\nx")
    qtbot.waitUntil(lambda: tab.list_widget.count() == 1, timeout=2000)
