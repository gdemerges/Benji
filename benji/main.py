import sys
import signal
import threading
from datetime import datetime
from queue import Queue

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import QTimer

from benji.config import AudioConfig, VADConfig, STTConfig, UIConfig
from benji.audio.capture import AudioCapture
from benji.audio.vad import VADProcessor
from benji.stats import SessionStats
from benji.stt.transcriber import Transcriber
from benji.ui.overlay import SubtitleOverlay
from benji.ui.history_window import HistoryWindow
from benji.ui.live_summary_window import LiveSummaryWindow


def main():
    audio_config = AudioConfig()
    vad_config = VADConfig()
    stt_config = STTConfig()
    ui_config = UIConfig()

    stats = SessionStats()
    session_start = stats.session_start

    audio_queue = Queue(maxsize=100)
    transcribe_queue = Queue(maxsize=3)
    display_queue = Queue(maxsize=10)

    capture = AudioCapture(audio_queue, audio_config)
    vad = VADProcessor(audio_queue, transcribe_queue, audio_config, vad_config, display_queue)
    transcriber = Transcriber(
        transcribe_queue, display_queue, stt_config,
        stats=stats, sample_rate=audio_config.sample_rate,
    )

    vad_thread = threading.Thread(target=vad.run, daemon=True, name="VAD")
    stt_thread = threading.Thread(target=transcriber.run, daemon=True, name="STT")

    print("[Benji] Starting...")
    vad_thread.start()
    stt_thread.start()
    capture.start()

    app = QApplication(sys.argv)
    app.setApplicationName("Benji")

    def qt_exception_hook(exc_type, exc_value, exc_traceback):
        if not issubclass(exc_type, KeyboardInterrupt):
            print(f"[Error] Uncaught exception: {exc_type.__name__}: {exc_value}")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def unraisable_hook(unraisable):
        print(f"[Error] Unraisable exception: {unraisable.exc_type.__name__}: {unraisable.exc_value}")

    sys.excepthook = qt_exception_hook
    sys.unraisablehook = unraisable_hook

    overlay = SubtitleOverlay(display_queue, ui_config)

    history_window = HistoryWindow(session_start=session_start, stats=stats)
    history_window.hide()

    live_summary_window = LiveSummaryWindow()
    live_summary_window.hide()

    # Optional: rolling live summary
    live_summarizer = None
    if stt_config.live_summary_interval_s > 0:
        from benji.llm.live_summary import LiveSummarizer
        live_summarizer = LiveSummarizer(
            interval_seconds=stt_config.live_summary_interval_s,
            session_start=session_start,
            on_summary=live_summary_window.on_summary,
        )
        live_summarizer.start()

    def _toggle(window):
        window.show() if window.isHidden() else window.hide()

    history_shortcut = QShortcut(QKeySequence("Ctrl+Shift+H"), overlay)
    history_shortcut.activated.connect(lambda: _toggle(history_window))

    summary_shortcut = QShortcut(QKeySequence("Ctrl+Shift+S"), overlay)
    summary_shortcut.activated.connect(lambda: _toggle(live_summary_window))

    app.aboutToQuit.connect(lambda: overlay.cleanup() if not overlay._shutting_down else None)

    def signal_handler(sig, frame):
        print("\n[Benji] Interrupt received, shutting down...")
        overlay.cleanup()
        QTimer.singleShot(0, app.quit)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("[Benji] Ctrl+Shift+H: history · Ctrl+Shift+S: live summary")

    exit_code = app.exec()

    print("[Benji] Shutting down...")
    if live_summarizer:
        live_summarizer.stop()
    capture.stop()
    audio_queue.put(None)
    transcribe_queue.put(None)
    vad_thread.join(timeout=2)
    stt_thread.join(timeout=2)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
