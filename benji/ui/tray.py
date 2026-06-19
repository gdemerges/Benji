"""Menu-bar tray icon with Quit / Show History actions."""

import logging
import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

log = logging.getLogger(__name__)


class _BillingActions(QObject):
    """Lance les appels de facturation hors du thread Qt et remonte les erreurs.

    Le réseau (checkout/portail) ne doit jamais bloquer la boucle Qt ; on émet
    `failed` (signal Qt → délivré sur le thread principal) pour notifier l'UI.
    """

    failed = pyqtSignal(str)

    def __init__(self, llm_cfg, parent=None):
        super().__init__(parent)
        self._cfg = llm_cfg

    def _run(self, fn) -> None:
        def worker():
            try:
                fn(self._cfg)
            except Exception as e:  # réseau, 401/402, backend down…
                log.warning("Facturation: %s", e)
                self.failed.emit(str(e))

        threading.Thread(target=worker, daemon=True, name="benji-billing").start()

    def open_checkout(self) -> None:
        from benji import billing
        self._run(billing.open_checkout)

    def open_portal(self) -> None:
        from benji import billing
        self._run(billing.open_portal)


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


def build_tray(
    history_window,
    live_summary_window,
    show_main_window=None,
    llm_cfg=None,
) -> QSystemTrayIcon:
    """show_main_window: callable() — when present, adds an 'Afficher fenêtre' item
    that invokes this callback. The caller is expected to route through the
    WindowController so overlay/window mutual exclusion is preserved.

    llm_cfg: LLMConfig — when it carries a backend token, adds 'Passer Pro…' /
    'Gérer l'abonnement…' items wired to Stripe via the backend.
    """
    tray = QSystemTrayIcon(_make_icon())
    tray.setToolTip("Benji — live subtitles")

    menu = QMenu()

    if show_main_window is not None:
        show_main = QAction("Afficher fenêtre", menu)
        show_main.triggered.connect(show_main_window)
        menu.addAction(show_main)

    show_history = QAction("Afficher l'historique", menu)
    show_history.triggered.connect(history_window.show)
    menu.addAction(show_history)

    show_summary = QAction("Résumé en direct", menu)
    show_summary.triggered.connect(live_summary_window.show)
    menu.addAction(show_summary)

    # Facturation Stripe (seulement si un compte backend est configuré).
    if llm_cfg is not None and getattr(llm_cfg, "backend_token", None):
        billing = _BillingActions(llm_cfg, parent=tray)
        billing.failed.connect(
            lambda msg: tray.showMessage(
                "Benji — abonnement",
                f"Action impossible : {msg}",
                QSystemTrayIcon.MessageIcon.Warning,
            )
        )
        tray._billing = billing  # garde une référence (sinon GC)

        menu.addSeparator()
        go_pro = QAction("Passer Pro…", menu)
        go_pro.triggered.connect(billing.open_checkout)
        menu.addAction(go_pro)

        manage = QAction("Gérer l'abonnement…", menu)
        manage.triggered.connect(billing.open_portal)
        menu.addAction(manage)

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
