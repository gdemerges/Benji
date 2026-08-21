"""Rendu markdown partagé — les résumés s'affichent, ils ne se lisent pas en source.

Le même rendu sert à l'onglet Résumés et à la fenêtre Résumé en direct. Cette
dernière affichait jusqu'ici le markdown brut dans une boîte monospace : on y
lisait `**Décision**` au lieu de voir une décision. Deux surfaces qui montrent le
même objet doivent le montrer de la même façon.

`QTextBrowser.setMarkdown` ignore les marges CSS des titres ; elles sont donc
reposées sur les `QTextBlockFormat` après rendu (cf. `render_markdown`).
"""

from __future__ import annotations

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QTextBrowser

from benji.ui.style import FONT_DISPLAY, FONT_MONO, FONT_READING, FONT_UI, Theme, reading_font

# Marges (haut, bas) en px par niveau de titre.
_HEADING_MARGINS = {1: (2, 12), 2: (22, 8), 3: (16, 6)}


def _rgba(color) -> str:
    return f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha()})"


def markdown_css(theme: Theme) -> str:
    """Feuille de style d'un résumé : titres en SF Pro, corps dans la face à lire.

    Un résumé est un texte suivi, pas une fiche technique : il est composé dans
    la même face que le transcript, pour que l'app garde une seule voix pour tout
    ce qui vient de la réunion.
    """
    code_bg = _rgba(theme.ink_alpha(7))
    return f"""
        body {{
            font-family: {FONT_READING};
            font-size: 15px;
            line-height: 1.7;
            color: {_rgba(theme.ink)};
            padding: 20px 24px;
        }}
        h1 {{ font-family: {FONT_DISPLAY}; font-size: 21px; font-weight: 600; margin: 0 0 16px 0; }}
        h2 {{ font-family: {FONT_UI}; font-size: 15px; font-weight: 700; margin: 20px 0 10px 0; }}
        h3 {{ font-family: {FONT_UI}; font-size: 13px; font-weight: 700; margin: 16px 0 8px 0; }}
        p {{ margin: 0 0 12px 0; }}
        strong {{ font-weight: 700; }}
        code {{
            font-family: {FONT_MONO}; font-size: 13px;
            background-color: {code_bg}; padding: 1px 5px; border-radius: 3px;
        }}
        pre {{ background-color: {code_bg}; padding: 10px 14px; border-radius: 6px; }}
        pre code {{ background: transparent; padding: 0; }}
        blockquote {{
            border-left: 2px solid {_rgba(theme.spine)};
            padding-left: 14px; color: {_rgba(theme.ink_muted)}; margin: 12px 0;
        }}
        ul, ol {{ margin: 0 0 12px 18px; padding: 0; }}
        li {{ margin-bottom: 5px; }}
        a {{ color: {_rgba(theme.ink)}; text-decoration: underline; }}
    """


def render_markdown(browser: QTextBrowser, text: str) -> None:
    """Rend `text` puis repose les marges de titre que le CSS ne peut pas fixer."""
    browser.setMarkdown(text)
    doc = browser.document()
    block = doc.begin()
    while block.isValid():
        level = block.blockFormat().headingLevel()
        if level in _HEADING_MARGINS:
            top, bottom = _HEADING_MARGINS[level]
            fmt = block.blockFormat()
            fmt.setTopMargin(top)
            fmt.setBottomMargin(bottom)
            QTextCursor(block).setBlockFormat(fmt)
        block = block.next()


class MarkdownView(QTextBrowser):
    """Panneau de lecture markdown, transparent, sans cadre."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setOpenExternalLinks(True)
        self.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        self.document().setDefaultFont(reading_font())
        self.document().setDocumentMargin(20)

    def apply_theme(self, theme: Theme) -> None:
        self.setStyleSheet("QTextBrowser { background: transparent; border: none; }")
        self.document().setDefaultStyleSheet(markdown_css(theme))
        # Re-rendre pour que la nouvelle feuille prenne : le document garde son
        # markdown source, pas le HTML déjà composé.
        current = self.property("_markdown_source") or ""
        if current:
            render_markdown(self, current)

    def set_markdown(self, text: str) -> None:
        self.setProperty("_markdown_source", text)
        render_markdown(self, text)
