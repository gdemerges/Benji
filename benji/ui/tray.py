"""Menu-bar tray icon: Quit / Show History / account & Stripe billing."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from benji.ui.account_controller import AccountController

log = logging.getLogger(__name__)


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
    icon = QIcon(pix)
    # Template image macOS : le système recolore le glyphe (noir attendu) selon
    # le thème de la barre de menus — sinon le « B » est invisible en dark mode.
    # Sans effet sur les autres plateformes.
    icon.setIsMask(True)
    return icon


def _build_account_section(menu: QMenu, account: AccountController) -> None:
    """(Re)peuple la section compte du menu selon l'état de connexion."""
    menu.addSeparator()
    if account.session.is_authenticated:
        email = QAction(account.session.email or "Connecté", menu)
        email.setEnabled(False)
        menu.addAction(email)

        go_pro = QAction("Passer Pro…", menu)
        go_pro.triggered.connect(account.open_checkout)
        menu.addAction(go_pro)

        manage = QAction("Gérer l'abonnement…", menu)
        manage.triggered.connect(account.open_portal)
        menu.addAction(manage)

        logout = QAction("Se déconnecter", menu)
        logout.triggered.connect(account.logout)
        menu.addAction(logout)
    else:
        login = QAction("Se connecter…", menu)
        # lambda : QAction.triggered émet un bool `checked` qu'on ne veut pas
        # voir arriver dans le paramètre `parent` de login().
        login.triggered.connect(lambda: account.login())
        menu.addAction(login)


def build_tray(
    history_window,
    live_summary_window,
    show_main_window=None,
    session=None,
    backend_url: str = "",
    open_preferences=None,
) -> QSystemTrayIcon:
    """show_main_window: callable() — when present, adds an 'Afficher fenêtre' item
    that invokes this callback. The caller is expected to route through the
    WindowController so overlay/window mutual exclusion is preserved.

    session: benji.account.Session — when present, adds an account section
    (login/logout) and, once connected, Stripe billing items. The subscription
    follows the account across platforms.
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

    if open_preferences is not None:
        prefs = QAction("Préférences…", menu)
        prefs.triggered.connect(open_preferences)
        menu.addAction(prefs)

    if session is not None:
        def _notify(title: str, msg: str) -> None:
            tray.showMessage(f"Benji — {title}", msg,
                             QSystemTrayIcon.MessageIcon.Information)

        account = AccountController(session, backend_url, _notify, parent=tray)
        account.failed.connect(
            lambda msg: tray.showMessage(
                "Benji — abonnement",
                f"Action impossible : {msg}",
                QSystemTrayIcon.MessageIcon.Warning,
            )
        )
        tray._account = account  # garde une référence (sinon GC)

        # La section compte change selon l'état (connecté/déconnecté) : on la
        # reconstruit à chaque ouverture du menu, après le tronc commun
        # (fenêtre/historique/résumé).
        trunk = len(menu.actions())
        quit_action = _make_quit_action(menu)

        def _rebuild():
            for action in menu.actions()[trunk:]:
                menu.removeAction(action)
            _build_account_section(menu, account)
            menu.addSeparator()
            menu.addAction(quit_action)

        menu.aboutToShow.connect(_rebuild)
        _rebuild()
    else:
        menu.addSeparator()
        menu.addAction(_make_quit_action(menu))

    tray.setContextMenu(menu)
    tray.show()
    return tray


def _make_quit_action(menu: QMenu) -> QAction:
    def _hard_quit():
        import os
        QApplication.quit()
        # Belt-and-suspenders: daemon threads (VAD/STT/watchdog) may hold the
        # event loop a beat longer than desired with a tray icon active.
        os._exit(0)

    quit_action = QAction("Quitter Benji", menu)
    quit_action.triggered.connect(_hard_quit)
    return quit_action
