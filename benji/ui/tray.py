"""Menu-bar tray icon: Quit / Show History / account & Stripe billing."""

import logging
import subprocess
import sys

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from benji.logging_config import log_dir, log_file_path
from benji.report import build_mailto_url
from benji.ui.account_controller import AccountController

log = logging.getLogger(__name__)


def report_problem(stats=None, stt_config=None) -> None:
    """Ouvre un brouillon de mail prérempli et révèle le log dans le Finder.

    Un `mailto:` ne peut pas porter de pièce jointe : les métriques (anonymes)
    partent dans le corps, et le log est révélé pour que l'utilisateur le joigne
    lui-même — il voit ainsi exactement ce qu'il envoie.
    """
    path = log_file_path()
    url = build_mailto_url(
        stats_snapshot=stats.snapshot() if stats is not None else None,
        stt_config=stt_config,
        log_path=str(path) if path.exists() else None,
    )
    QDesktopServices.openUrl(QUrl(url))
    if path.exists():
        reveal_logs()


def reveal_logs() -> None:
    """Montre le log dans le Finder — le seul canal de diag d'une app bundlée.

    `open -R` sélectionne le fichier dans son dossier ; si le handler fichier
    n'a pas pu être créé, on se rabat sur l'ouverture du dossier.
    """
    path = log_file_path()
    if sys.platform == "darwin" and path.exists():
        try:
            subprocess.run(["open", "-R", str(path)], check=True)
            return
        except (OSError, subprocess.CalledProcessError) as e:
            log.warning("Could not reveal log file: %s", e)

    target = path.parent if path.exists() else log_dir()
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


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
    toggle_pause=None,
    is_paused=None,
    stats=None,
    stt_config=None,
    mark_moment=None,
    save_meeting=None,
    is_saving=None,
    on_new_meeting=None,
) -> QSystemTrayIcon:
    """show_main_window: callable() — when present, adds an 'Afficher fenêtre' item
    that invokes this callback. The caller is expected to route through the
    WindowController so overlay/window mutual exclusion is preserved.

    session: benji.account.Session — when present, adds an account section
    (login/logout) and, once connected, Stripe billing items. The subscription
    follows the account across platforms.

    toggle_pause: callable() -> bool — bascule la pause micro et retourne le
    nouvel état. is_paused: callable() -> bool — état courant, relu à chaque
    ouverture du menu (la pause peut aussi être basculée depuis la fenêtre).

    stats: benji.stats.SessionStats — joint les métriques (anonymes) au rapport
    de bug. stt_config: STTConfig — y joint la config du moteur.

    save_meeting: callable() -> int — accorde la conservation de la réunion en
    cours et retourne le nombre d'entrées versées. is_saving: callable() -> bool
    — état courant, relu à l'ouverture du menu. Le raccourci du tray existe parce
    que la décision de garder se prend souvent sans quitter la visio, donc sans
    aller chercher la fenêtre (cf. benji/recording.py).
    """
    tray = QSystemTrayIcon(_make_icon())
    tray.setToolTip("Benji — live subtitles")

    menu = QMenu()

    if toggle_pause is not None:
        pause_action = QAction("Suspendre le micro", menu)

        def _refresh_pause_text(paused: bool) -> None:
            pause_action.setText("Reprendre le micro" if paused else "Suspendre le micro")

        pause_action.triggered.connect(lambda: _refresh_pause_text(bool(toggle_pause())))
        if is_paused is not None:
            menu.aboutToShow.connect(lambda: _refresh_pause_text(bool(is_paused())))
        menu.addAction(pause_action)
        menu.addSeparator()

    if mark_moment is not None:
        mark_action = QAction("Marquer ce moment", menu)

        def _mark() -> None:
            # En visio, le focus est sur Teams ou Zoom : c'est ici (et par le
            # raccourci global) que le geste est réellement à portée.
            marked = mark_moment()
            tray.showMessage(
                "Benji", "Moment marqué." if marked
                else "Rien à marquer — aucune phrase transcrite pour l'instant.",
                QSystemTrayIcon.MessageIcon.Information,
            )

        mark_action.triggered.connect(_mark)
        menu.addAction(mark_action)

    if save_meeting is not None:
        save_action = QAction("Conserver cette réunion", menu)

        def _refresh_save_state() -> None:
            saving = bool(is_saving()) if is_saving is not None else False
            save_action.setEnabled(not saving)
            save_action.setText(
                "Réunion conservée" if saving else "Conserver cette réunion"
            )

        def _save() -> None:
            versees = save_meeting()
            _refresh_save_state()
            # Un accord donné hors de la vue doit se voir confirmé : croire
            # qu'on garde alors que non est le pire des deux états.
            tray.showMessage(
                "Benji — réunion conservée",
                f"{versees} ligne(s) déjà dites ont été versées à l'historique."
                if versees else "Ce qui suit est écrit dans l'historique.",
                QSystemTrayIcon.MessageIcon.Information,
            )

        save_action.triggered.connect(_save)
        menu.aboutToShow.connect(_refresh_save_state)
        menu.addAction(save_action)
        menu.addSeparator()

    if show_main_window is not None:
        show_main = QAction("Afficher fenêtre", menu)
        show_main.triggered.connect(show_main_window)
        menu.addAction(show_main)

    show_history = QAction("Afficher l'historique", menu)
    show_history.triggered.connect(history_window.show)
    menu.addAction(show_history)

    # Clôt la réunion en cours : ce qui suit part dans une nouvelle. Sans ça, le
    # seul moyen de séparer deux réunions serait de redémarrer l'app.
    new_meeting = QAction("Nouvelle réunion", menu)

    def _start_new_meeting() -> None:
        from benji import meetings

        meeting = meetings.start_meeting()
        # L'accord de conservation ne se reporte pas d'une réunion à l'autre :
        # avoir accepté de garder celle de ce matin ne dit rien de la suivante.
        if on_new_meeting is not None:
            on_new_meeting()
        if hasattr(history_window, "reload_meetings"):
            history_window.reload_meetings()
        tray.showMessage("Benji — nouvelle réunion", meeting.title,
                         QSystemTrayIcon.MessageIcon.Information)

    new_meeting.triggered.connect(_start_new_meeting)
    menu.addAction(new_meeting)

    show_summary = QAction("Résumé en direct", menu)
    show_summary.triggered.connect(live_summary_window.show)
    menu.addAction(show_summary)

    if open_preferences is not None:
        prefs = QAction("Préférences…", menu)
        prefs.triggered.connect(open_preferences)
        menu.addAction(prefs)

    # Dans le tronc commun (avant la section compte) : `_rebuild` ne recycle que
    # les actions situées après `trunk`.
    report = QAction("Signaler un problème…", menu)
    report.triggered.connect(lambda: report_problem(stats=stats, stt_config=stt_config))
    menu.addAction(report)

    reveal = QAction("Révéler les logs", menu)
    reveal.triggered.connect(reveal_logs)
    menu.addAction(reveal)

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
