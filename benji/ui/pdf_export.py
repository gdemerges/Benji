"""Export PDF d'un compte rendu ou d'un résumé.

Les exports existants (`txt`, `md`, `srt`) sont des formats de travail : on les
rouvre dans un éditeur. Le PDF est le format qu'on **envoie** — à quelqu'un qui
n'a pas Benji, après une réunion, sans lui demander d'ouvrir un fichier
markdown. C'est la seule sortie de Benji qui soit un document fini.

Il est composé dans la **même feuille** que le reste (`markdown_css`), pour que
le document envoyé ressemble à la page qu'on regardait pendant la réunion — mais
toujours en variante **claire** : le papier est blanc chez tout le monde, et un
export du thème sombre donnerait un texte presque blanc sur fond blanc.

Qt fait le rendu ; la fonction reste sans dialogue ni fenêtre, donc testable en
tête-à-tête avec un chemin de fichier.
"""

from __future__ import annotations

from PyQt6.QtCore import QMarginsF, QSizeF
from PyQt6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from benji.ui.style import light_theme, reading_font
from benji.ui.widgets.markdown_view import apply_heading_margins, markdown_css

# A4 avec des marges de livre : un compte rendu se lit en colonne, pas en pleine
# largeur d'écran.
_MARGINS_MM = 18.0


def write_pdf(markdown_text: str, path, title: str = "") -> None:
    """Écrit *markdown_text* en PDF à *path*.

    Les marges de titre que `setMarkdown` ignore sont reposées comme à l'écran
    (`apply_heading_margins`), sinon les sections du compte rendu se colleraient
    les unes aux autres sur le papier.
    """
    writer = QPdfWriter(str(path))
    # 96 dpi et pas les 1200 par défaut : les tailles de `markdown_css` sont en
    # px, pensées pour un écran. À 1200 dpi la page fait ~9900 px de haut, un
    # corps de 15 px y devient microscopique et **tout le document tient sur une
    # seule page** — le PDF sortait illisible et non paginé. Le texte reste
    # vectoriel : la résolution ne fixe que l'unité de mise en page.
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(
        QMarginsF(_MARGINS_MM, _MARGINS_MM, _MARGINS_MM, _MARGINS_MM),
        QPageLayout.Unit.Millimeter,
    )
    if title:
        writer.setTitle(title)

    doc = QTextDocument()
    doc.setDefaultFont(reading_font())
    doc.setDefaultStyleSheet(markdown_css(light_theme()))
    doc.setMarkdown(markdown_text)
    apply_heading_margins(doc)
    # Sans taille de page explicite, le document se compose sur une seule page
    # infiniment haute et le PDF ne contient que le premier écran.
    doc.setPageSize(QSizeF(writer.width(), writer.height()))
    doc.print(writer)
