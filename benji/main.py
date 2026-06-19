import logging
import platform
import signal
import sys
import threading
from queue import Queue

from benji.logging_config import setup_logging

setup_logging()
log = logging.getLogger(__name__)


def _promote_to_accessory_app():
    """Convert the process to an 'accessory' app BEFORE any Qt/AppKit init.

    On macOS 13+ this is required for a window to float over another app's
    native fullscreen Space. Must run before QApplication is instantiated,
    otherwise Qt locks the activation policy to 'regular'.
    """
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
    except Exception as e:
        logging.getLogger("benji.main").warning("Could not set accessory policy: %s", e)


_promote_to_accessory_app()

from PyQt6.QtCore import QEventLoop, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication

from benji.audio.capture import AudioCapture
from benji.audio.vad import VADProcessor
from benji.config import AudioConfig, LLMConfig, STTConfig, UIConfig, VADConfig
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


def main():
    audio_config = AudioConfig()
    vad_config = VADConfig()
    stt_config = STTConfig()
    ui_config = UIConfig()
    llm_config = LLMConfig()

    stats = SessionStats()
    session_start = stats.session_start

    audio_queue = Queue(maxsize=100)
    transcribe_queue = Queue(maxsize=3)
    display_queue = Queue(maxsize=10)

    capture = AudioCapture(audio_queue, audio_config)
    vad = VADProcessor(audio_queue, transcribe_queue, audio_config, vad_config, display_queue, stats=stats)

    log.info("Starting...")

    app = QApplication(sys.argv)
    app.setApplicationName("Benji")

    remote_mode = stt_config.stt_provider == "remote"

    # Splash: load Whisper on a background thread so the UI stays responsive
    # and the user sees clear progress instead of a frozen process.
    splash = SplashWindow()
    splash.set_status(
        "Connexion au service de transcription…" if remote_mode
        else f"Chargement du modèle Whisper '{stt_config.model_size}'…"
    )
    splash.show()
    app.processEvents()

    transcriber = None
    remote_stt = None
    history = None
    vad_thread = None
    stt_supervisor = None
    remote_thread = None
    stt_stopping = threading.Event()

    if remote_mode:
        # Transcription côté backend : pas de Whisper, pas de VAD. Le micro est
        # streamé au backend, dont les events alimentent display_queue.
        from benji.history import TranscriptionHistory
        from benji.stt.remote import build_remote_stt_client
        history = TranscriptionHistory()
        remote_stt = build_remote_stt_client(
            audio_queue, display_queue, history, stt_config, llm_config,
            sample_rate=audio_config.sample_rate,
        )
    else:
        class _ModelLoader(QThread):
            loaded = pyqtSignal(object)
            failed = pyqtSignal(object)
            warming = pyqtSignal()

            def run(self):
                try:
                    t = Transcriber(
                        transcribe_queue, display_queue, stt_config,
                        stats=stats, sample_rate=audio_config.sample_rate,
                    )
                    self.warming.emit()
                    t.warmup()
                    self.loaded.emit(t)
                except Exception as e:
                    self.failed.emit(e)

        loader = _ModelLoader()
        loop = QEventLoop()
        transcriber_holder: dict = {}
        load_error: dict = {}
        loader.loaded.connect(lambda t: (transcriber_holder.__setitem__("t", t), loop.quit()))
        loader.failed.connect(lambda e: (load_error.__setitem__("e", e), loop.quit()))
        loader.warming.connect(lambda: splash.set_status("Préchauffage du modèle…"))
        loader.start()
        loop.exec()
        loader.wait()

        if "e" in load_error:
            splash.close()
            raise load_error["e"]

        transcriber = transcriber_holder["t"]
        history = transcriber.history

    splash.set_status("Démarrage de la capture audio…")
    app.processEvents()

    if remote_mode:
        remote_thread = threading.Thread(
            target=remote_stt.run, daemon=True, name="RemoteSTT"
        )
        remote_thread.start()
    else:
        vad_thread = threading.Thread(target=vad.run, daemon=True, name="VAD")

        # Supervisor: restart the STT thread if it dies. The transcriber's run loop
        # already catches per-segment errors; this is the last-resort safety net for
        # anything that escapes (e.g. backend crash, OOM in a tokenizer).
        stt_thread_ref: dict = {}

        def _stt_supervisor():
            backoff = 1.0
            while not stt_stopping.is_set():
                t = threading.Thread(target=transcriber.run, daemon=True, name="STT")
                stt_thread_ref["t"] = t
                t.start()
                t.join()
                if stt_stopping.is_set():
                    return
                log.error("STT thread exited unexpectedly; restarting in %.1fs", backoff)
                if stats is not None:
                    stats.record_drop("stt_thread_restart")
                stt_stopping.wait(timeout=backoff)
                backoff = min(backoff * 2, 30.0)

        stt_supervisor = threading.Thread(
            target=_stt_supervisor, daemon=True, name="STT-supervisor"
        )
        vad_thread.start()
        stt_supervisor.start()

    capture.start()
    splash.close()

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

    bus = DisplayBus(display_queue)
    bus.start()

    # Mode de lancement détecté ici pour configurer l'overlay en interactif si .app
    _mode = launch_mode()
    overlay = SubtitleOverlay(bus, ui_config, interactive=(_mode == "window"))

    history_window = HistoryWindow(session_start=session_start, stats=stats)
    history_window.hide()

    live_summary_window = LiveSummaryWindow()
    live_summary_window.hide()

    # Mode de lancement : CLI overlay-seul vs .app fenêtre principale
    mode = _mode
    log.info("Launch mode: %s", mode)

    main_window = None
    controller = None
    summary_worker = None

    if mode == "window":
        summary_worker = SummaryWorker(provider=build_summary_provider(llm_config))
        summary_worker.start()

        main_window = MainWindow(
            bus=bus,
            history=history,
            session_start=session_start,
            summary_worker=summary_worker,
            on_minimize=lambda: controller.show_overlay() if controller else None,
        )

        controller = WindowController(
            main_window=main_window,
            overlay=overlay,
            initial_mode="window",
        )

        # Click sur overlay → revient à la fenêtre
        overlay._on_click = lambda: controller.show_window()

    # Menu-bar tray icon (Quit / Show history / Show summary / Show window in .app mode)
    _show_main_cb = (lambda: controller.show_window()) if controller is not None else None
    tray = build_tray(history_window, live_summary_window, show_main_window=_show_main_cb, llm_cfg=llm_config)  # noqa: F841 (keep ref)

    # Optional: rolling live summary
    live_summarizer = None
    if stt_config.live_summary_interval_s > 0:
        from benji.llm.live_summary import LiveSummarizer
        live_summarizer = LiveSummarizer(
            interval_seconds=stt_config.live_summary_interval_s,
            session_start=session_start,
            on_summary=live_summary_window.on_summary,
            on_summary_start=live_summary_window.on_summary_start,
            on_summary_chunk=live_summary_window.on_summary_chunk,
        )
        live_summarizer.start()

    def _toggle(window):
        window.show() if window.isHidden() else window.hide()

    history_shortcut = QShortcut(QKeySequence("Ctrl+Shift+H"), overlay)
    history_shortcut.activated.connect(lambda: _toggle(history_window))

    summary_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), overlay)
    summary_shortcut.activated.connect(lambda: _toggle(live_summary_window))

    # Diagnostic: Ctrl+Shift+D dumps current macOS window state
    if platform.system() == "Darwin":
        debug_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), overlay)
        debug_shortcut.activated.connect(
            lambda: overlay._apply_macos_window_settings(verbose=True)
        )

    app.aboutToQuit.connect(lambda: overlay.cleanup() if not overlay._shutting_down else None)

    def signal_handler(sig, frame):
        log.info("Interrupt received, shutting down...")
        overlay.cleanup()
        QTimer.singleShot(0, app.quit)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log.info("Ctrl+Shift+H: history · Ctrl+Shift+S: live summary")

    exit_code = app.exec()

    log.info("Shutting down...")
    if summary_worker is not None:
        summary_worker.shutdown()
    bus.stop()
    if live_summarizer:
        live_summarizer.stop()
    capture.stop()
    audio_queue.put(None)
    stt_stopping.set()
    if remote_stt is not None:
        remote_stt.stop()
    if not remote_mode:
        transcribe_queue.put(None)
    if vad_thread is not None:
        vad_thread.join(timeout=2)
    if stt_supervisor is not None:
        stt_supervisor.join(timeout=3)
    if remote_thread is not None:
        remote_thread.join(timeout=2)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
