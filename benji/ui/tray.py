"""Menu-bar tray icon with Quit / Show History actions."""

from PyQt6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication


def _make_icon() -> QIcon:
    """Render a tiny 'B' glyph as the tray icon (template-style)."""
    pix = QPixmap(22, 22)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(0, 0, 0, 230))
    p.setFont(QFont(".AppleSystemUIFont", 15, QFont.Weight.Bold))
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "B")
    p.end()
    return QIcon(pix)


def build_tray(history_window, live_summary_window) -> QSystemTrayIcon:
    tray = QSystemTrayIcon(_make_icon())
    tray.setToolTip("Benji — live subtitles")

    menu = QMenu()

    show_history = QAction("Afficher l'historique", menu)
    show_history.triggered.connect(history_window.show)
    menu.addAction(show_history)

    show_summary = QAction("Résumé en direct", menu)
    show_summary.triggered.connect(live_summary_window.show)
    menu.addAction(show_summary)

    menu.addSeparator()

    def _hard_quit():
        import os
        QApplication.quit()
        # Belt-and-suspenders: daemon threads (VAD/STT/watchdog) may hold the
        # event loop a beat longer than desired with a tray icon active.
        os._exit(0)

    quit_action = QAction("Quitter Benji", menu)
    quit_action.triggered.connect(_hard_quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()
    return tray
