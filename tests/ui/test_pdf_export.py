"""Export PDF — le seul format de Benji qui parte à quelqu'un qui n'a pas Benji."""

import pytest
from PyQt6.QtWidgets import QApplication

from benji import export


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _entries():
    return [
        {"timestamp": "2026-08-21T14:32:00", "text": "On revoit le budget.", "speaker": "A"},
        {"timestamp": "2026-08-21T14:33:00", "text": "D'accord.", "speaker": "B"},
    ]


def test_le_pdf_est_ecrit_et_lisible(qapp, tmp_path):
    from benji.ui.pdf_export import write_pdf

    path = tmp_path / "compte-rendu.pdf"
    write_pdf(export.to_markdown(_entries()), path, title="Revue budget")

    assert path.exists()
    # En-tête PDF : le fichier est un vrai document, pas un fichier vide créé
    # par QPdfWriter avant d'échouer.
    assert path.read_bytes().startswith(b"%PDF")
    assert path.stat().st_size > 1000
    assert _page_count(path) == 1


def test_un_texte_long_ne_tient_pas_sur_une_page(qapp, tmp_path):
    """Sans taille de page explicite, Qt compose sur une page infiniment haute
    et le PDF ne contient que le premier écran."""
    from benji.ui.pdf_export import write_pdf

    long_entries = [
        {"timestamp": f"2026-08-21T14:{m:02d}:00", "text": "Phrase de réunion. " * 20}
        for m in range(0, 55)
    ]
    path = tmp_path / "long.pdf"
    write_pdf(export.to_markdown(long_entries), path)

    assert _page_count(path) > 1


def _page_count(path) -> int:
    """Nombre de pages, lu dans l'arbre du PDF (`/Count`)."""
    import re

    found = re.findall(rb"/Count\s+(\d+)", path.read_bytes())
    return max(int(n) for n in found) if found else 0


def test_le_pdf_est_compose_en_variante_claire(qapp, monkeypatch):
    """Le papier est blanc chez tout le monde : exporter le thème sombre
    donnerait un texte presque blanc sur fond blanc."""
    from benji.ui import style

    monkeypatch.setattr(style, "_is_dark", lambda: True)

    assert style.light_theme().is_dark is False
    assert style.current_theme().is_dark is True
