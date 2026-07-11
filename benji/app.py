"""Composition root de Benji : câble configs → pipeline → threads → UI.

`main.py` reste un point d'entrée mince ; toute l'orchestration du démarrage et
de l'arrêt vit ici, découpée en phases lisibles et pilotables. Chaque phase est
une méthode : on peut en stubber une poignée (Qt, audio, chargement du modèle)
pour tester la composition sans lancer réellement l'app.

IMPORTANT macOS : la politique « accessory » doit être posée AVANT `QApplication`
(cf. main.py) — ce module suppose que c'est déjà fait au moment où `run()` crée
le `QApplication`.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from dataclasses import dataclass, field
from queue import Queue

from PyQt6.QtCore import QEventLoop, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication

from benji.audio.capture import AudioCapture
from benji.audio.vad import VADProcessor
from benji.config import (
    IS_MACOS,
    AudioConfig,
    LLMConfig,
    STTConfig,
    UIConfig,
    VADConfig,
)
from benji.launch_mode import launch_mode
from benji.llm.providers import build_summary_provider
from benji.llm.summary_worker import SummaryWorker
from benji.stats import SessionStats
from benji.stt.transcriber import Transcriber
from benji.ui.display_bus import DisplayBus
from benji.ui.history_window import HistoryWindow
from benji.ui.live_summary_window import LiveSummaryWindow
from benji.ui.main_window import MainWindow
from benji.ui.overlay import SubtitleOverlay
from benji.ui.splash import SplashWindow
from benji.ui.tray import build_tray
from benji.ui.window_controller import WindowController

log = logging.getLogger(__name__)


@dataclass
class AppConfigs:
    """Les cinq dataclasses de config, regroupées pour l'injection/les tests."""

    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)


class BenjiApplication:
    """État + orchestration du cycle de vie de l'app (démarrage → exec → arrêt)."""

    def __init__(self, configs: AppConfigs | None = None):
        self.cfg = configs or AppConfigs()

        # Renseignés au fil des phases de run().
        self.user_settings = None
        self.session = None
        self.stats: SessionStats | None = None
        self.session_start = None

        self.audio_queue: Queue | None = None
        self.transcribe_queue: Queue | None = None
        self.display_queue: Queue | None = None
        self.capture: AudioCapture | None = None
        self.vad: VADProcessor | None = None

        self.app: QApplication | None = None
        self.remote_mode = False

        self.transcriber: Transcriber | None = None
        self.remote_stt = None
        self.history = None

        self.vad_thread: threading.Thread | None = None
        self.stt_supervisor: threading.Thread | None = None
        self.remote_thread: threading.Thread | None = None
        self.stt_stopping = threading.Event()

        self.bus: DisplayBus | None = None
        self.overlay: SubtitleOverlay | None = None
        self.history_window: HistoryWindow | None = None
        self.live_summary_window: LiveSummaryWindow | None = None

        self.mode = "overlay"
        self.main_window: MainWindow | None = None
        self.controller: WindowController | None = None
        self.summary_worker: SummaryWorker | None = None
        self.live_summarizer = None
        self.tray = None
        self._shortcuts: list[QShortcut] = []  # garder les refs (sinon GC)

    # --- orchestration ---

    def run(self) -> int:
        """Démarre l'app, entre dans la boucle Qt, puis arrête proprement."""
        self._build_configs()
        self._build_account()
        self._build_pipeline()
        self._create_qapp()

        splash = self._show_splash()
        try:
            self._load_transcriber(splash)
        except Exception:
            splash.close()
            raise
        self._start_stt()
        self.capture.start()
        splash.close()

        self._install_excepthooks()
        self._build_display()
        self._build_windows()
        self._build_tray_and_shortcuts()
        self._install_signal_handlers()

        log.info("Ctrl+Shift+H: history · Ctrl+Shift+S: live summary")
        exit_code = self.app.exec()

        self.shutdown()
        return exit_code

    # --- phases ---

    def _build_configs(self) -> None:
        # Préférences persistées (QSettings) : appliquées AVANT le chargement du
        # modèle pour que langue/taille de modèle prennent effet.
        from benji.settings import UserSettings

        self.user_settings = UserSettings()
        self.user_settings.hydrate(stt=self.cfg.stt, ui=self.cfg.ui, llm=self.cfg.llm)

    def _build_account(self) -> None:
        # Compte Benji : si une session est enregistrée, on injecte son access
        # token pour les appels backend. L'abonnement suit le compte, pas le poste.
        from benji.account import build_session

        self.session = build_session(self.cfg.llm.backend_url)
        token = self.session.access_token()
        if token:
            self.cfg.llm.backend_token = token

    def _build_pipeline(self) -> None:
        # Calculé ici (et pas dans _create_qapp) : le choix local/remote pilote
        # la construction du pipeline, avant même la création du QApplication.
        self.remote_mode = self.cfg.stt.stt_provider == "remote"

        self.stats = SessionStats()
        self.session_start = self.stats.session_start

        self.audio_queue = Queue(maxsize=100)
        self.transcribe_queue = Queue(maxsize=3)
        self.display_queue = Queue(maxsize=10)

        self.capture = AudioCapture(self.audio_queue, self.cfg.audio, stats=self.stats)
        if not self.remote_mode:
            # En mode remote le VAD n'est jamais démarré : inutile de charger
            # le modèle Silero ONNX (fait dans VADProcessor.__init__).
            self.vad = VADProcessor(
                self.audio_queue, self.transcribe_queue, self.cfg.audio, self.cfg.vad,
                self.display_queue, stats=self.stats,
            )
        log.info("Starting...")

    def _create_qapp(self) -> None:
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Benji")

    def _show_splash(self) -> SplashWindow:
        # Load Whisper on a background thread so the UI stays responsive and the
        # user sees clear progress instead of a frozen process.
        splash = SplashWindow()
        splash.set_status(
            "Connexion au service de transcription…" if self.remote_mode
            else f"Chargement du modèle Whisper '{self.cfg.stt.model_size}'…"
        )
        splash.show()
        self.app.processEvents()
        return splash

    def _load_transcriber(self, splash: SplashWindow) -> None:
        if self.remote_mode:
            # Transcription côté backend : pas de Whisper, pas de VAD. Le micro est
            # streamé au backend, dont les events alimentent display_queue.
            from benji.history import TranscriptionHistory
            from benji.stt.remote import build_remote_stt_client

            self.history = TranscriptionHistory()
            self.remote_stt = build_remote_stt_client(
                self.audio_queue, self.display_queue, self.history,
                self.cfg.stt, self.cfg.llm, sample_rate=self.cfg.audio.sample_rate,
                # Rafraîchi à chaque (re)connexion : l'access token expire en 15 min.
                token_provider=self.session.access_token if self.session else None,
            )
            splash.set_status("Démarrage de la capture audio…")
            self.app.processEvents()
            return

        # Locals captured by the loader thread (avoid touching self off-thread).
        transcribe_queue = self.transcribe_queue
        display_queue = self.display_queue
        stats = self.stats
        stt_cfg = self.cfg.stt
        sample_rate = self.cfg.audio.sample_rate

        class _ModelLoader(QThread):
            loaded = pyqtSignal(object)
            failed = pyqtSignal(object)
            warming = pyqtSignal()

            def run(self):
                try:
                    t = Transcriber(
                        transcribe_queue, display_queue, stt_cfg,
                        stats=stats, sample_rate=sample_rate,
                    )
                    self.warming.emit()
                    t.warmup()
                    self.loaded.emit(t)
                except Exception as e:
                    self.failed.emit(e)

        loader = _ModelLoader()
        loop = QEventLoop()
        holder: dict = {}
        error: dict = {}
        loader.loaded.connect(lambda t: (holder.__setitem__("t", t), loop.quit()))
        loader.failed.connect(lambda e: (error.__setitem__("e", e), loop.quit()))
        loader.warming.connect(lambda: splash.set_status("Préchauffage du modèle…"))
        loader.start()
        loop.exec()
        loader.wait()

        if "e" in error:
            raise error["e"]

        self.transcriber = holder["t"]
        self.history = self.transcriber.history

        splash.set_status("Démarrage de la capture audio…")
        self.app.processEvents()

    def _start_stt(self) -> None:
        if self.remote_mode:
            self.remote_thread = threading.Thread(
                target=self.remote_stt.run, daemon=True, name="RemoteSTT"
            )
            self.remote_thread.start()
            return

        self.vad_thread = threading.Thread(target=self.vad.run, daemon=True, name="VAD")
        self.stt_supervisor = threading.Thread(
            target=self._stt_supervisor_loop, daemon=True, name="STT-supervisor"
        )
        self.vad_thread.start()
        self.stt_supervisor.start()

    def _stt_supervisor_loop(self) -> None:
        # Supervisor: restart the STT thread if it dies. The transcriber's run loop
        # already catches per-segment errors; this is the last-resort safety net for
        # anything that escapes (e.g. backend crash, OOM in a tokenizer).
        backoff = 1.0
        while not self.stt_stopping.is_set():
            t = threading.Thread(target=self.transcriber.run, daemon=True, name="STT")
            t.start()
            t.join()
            if self.stt_stopping.is_set():
                return
            log.error("STT thread exited unexpectedly; restarting in %.1fs", backoff)
            if self.stats is not None:
                self.stats.record_drop("stt_thread_restart")
            self.stt_stopping.wait(timeout=backoff)
            backoff = min(backoff * 2, 30.0)

    def _install_excepthooks(self) -> None:
        def qt_exception_hook(exc_type, exc_value, exc_traceback):
            if not issubclass(exc_type, KeyboardInterrupt):
                log.error("Uncaught exception: %s: %s", exc_type.__name__, exc_value)
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

        def unraisable_hook(unraisable):
            log.error(
                "Unraisable exception: %s: %s",
                unraisable.exc_type.__name__,
                unraisable.exc_value,
            )

        sys.excepthook = qt_exception_hook
        sys.unraisablehook = unraisable_hook

    def _build_display(self) -> None:
        self.bus = DisplayBus(self.display_queue)
        self.bus.start()

        # Mode de lancement : CLI overlay-seul vs .app fenêtre principale.
        self.mode = launch_mode()
        self.overlay = SubtitleOverlay(
            self.bus, self.cfg.ui, interactive=(self.mode == "window")
        )
        log.info("Launch mode: %s", self.mode)

    def _open_preferences(self) -> None:
        from benji.ui.preferences_dialog import PreferencesDialog

        PreferencesDialog(
            self.cfg.stt, self.cfg.ui, self.user_settings,
            on_live_change=self.overlay.apply_config,
            llm_config=self.cfg.llm,
        ).exec()

    def toggle_pause(self) -> bool:
        """Bascule la pause micro. Retourne le nouvel état (True = en pause).

        La pause ferme réellement le stream d'entrée (l'indicateur micro macOS
        s'éteint). Appelé depuis le tray et la fenêtre principale — thread Qt.
        """
        if self.capture.is_paused:
            self.capture.resume()
        else:
            self.capture.pause()
            # L'utterance en cours ne sera jamais terminée : éteindre
            # l'indicateur « en écoute » de l'UI.
            if self.display_queue is not None:
                self.display_queue.put({"type": "vad_status", "speaking": False})
        paused = self.capture.is_paused
        if self.main_window is not None:
            self.main_window.set_paused(paused)
        return paused

    def _build_windows(self) -> None:
        self.history_window = HistoryWindow(session_start=self.session_start, stats=self.stats)
        self.history_window.hide()

        self.live_summary_window = LiveSummaryWindow()
        self.live_summary_window.hide()

        if self.mode != "window":
            return

        self.summary_worker = SummaryWorker(provider=build_summary_provider(self.cfg.llm))
        self.summary_worker.start()

        self.main_window = MainWindow(
            bus=self.bus,
            history=self.history,
            session_start=self.session_start,
            summary_worker=self.summary_worker,
            on_minimize=lambda: self.controller.show_overlay() if self.controller else None,
            on_open_preferences=self._open_preferences,
            on_toggle_pause=self.toggle_pause,
            session=self.session,
            backend_url=self.cfg.llm.backend_url,
        )
        self.controller = WindowController(
            main_window=self.main_window,
            overlay=self.overlay,
            initial_mode="window",
        )
        # Click sur overlay → revient à la fenêtre.
        self.overlay._on_click = lambda: self.controller.show_window()

    def _build_tray_and_shortcuts(self) -> None:
        show_main = (lambda: self.controller.show_window()) if self.controller else None
        self.tray = build_tray(
            self.history_window, self.live_summary_window,
            show_main_window=show_main, session=self.session,
            backend_url=self.cfg.llm.backend_url, open_preferences=self._open_preferences,
            toggle_pause=self.toggle_pause,
            is_paused=lambda: self.capture.is_paused,
        )

        # Optional: rolling live summary.
        if self.cfg.stt.live_summary_interval_s > 0:
            from benji.llm.live_summary import LiveSummarizer

            self.live_summarizer = LiveSummarizer(
                interval_seconds=self.cfg.stt.live_summary_interval_s,
                session_start=self.session_start,
                on_summary=self.live_summary_window.on_summary,
                on_summary_start=self.live_summary_window.on_summary_start,
                on_summary_chunk=self.live_summary_window.on_summary_chunk,
            )
            self.live_summarizer.start()

        self._add_shortcut("Ctrl+Shift+H", lambda: self._toggle(self.history_window))
        self._add_shortcut("Ctrl+Shift+S", lambda: self._toggle(self.live_summary_window))
        if IS_MACOS:
            # Diagnostic: dump current macOS window state on demand.
            self._add_shortcut(
                "Ctrl+Shift+D",
                lambda: self.overlay._apply_macos_window_settings(verbose=True),
            )

    def _add_shortcut(self, keys: str, slot) -> None:
        sc = QShortcut(QKeySequence(keys), self.overlay)
        sc.activated.connect(slot)
        self._shortcuts.append(sc)

    @staticmethod
    def _toggle(window) -> None:
        window.show() if window.isHidden() else window.hide()

    def _install_signal_handlers(self) -> None:
        self.app.aboutToQuit.connect(
            lambda: self.overlay.cleanup() if not self.overlay._shutting_down else None
        )
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, sig, frame) -> None:
        log.info("Interrupt received, shutting down...")
        self.overlay.cleanup()
        QTimer.singleShot(0, self.app.quit)

    def shutdown(self) -> None:
        log.info("Shutting down...")
        if self.summary_worker is not None:
            self.summary_worker.shutdown()
        if self.bus is not None:
            self.bus.stop()
        if self.live_summarizer:
            self.live_summarizer.stop()
        if self.capture is not None:
            self.capture.stop()
        if self.audio_queue is not None:
            self.audio_queue.put(None)
        self.stt_stopping.set()
        if self.remote_stt is not None:
            self.remote_stt.stop()
        if not self.remote_mode and self.transcribe_queue is not None:
            self.transcribe_queue.put(None)
        if self.vad_thread is not None:
            self.vad_thread.join(timeout=2)
        if self.stt_supervisor is not None:
            self.stt_supervisor.join(timeout=3)
        if self.remote_thread is not None:
            self.remote_thread.join(timeout=2)
