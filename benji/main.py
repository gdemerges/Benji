import sys
import signal
import threading
from queue import Queue

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import QTimer

from benji.config import AudioConfig, VADConfig, STTConfig, UIConfig
from benji.audio.capture import AudioCapture
from benji.audio.vad import VADProcessor
from benji.stt.transcriber import Transcriber
from benji.ui.overlay import SubtitleOverlay
from benji.ui.history_window import HistoryWindow


def main():
    # Configs
    audio_config = AudioConfig()
    vad_config = VADConfig()
    stt_config = STTConfig()
    ui_config = UIConfig()

    # Queues
    audio_queue = Queue(maxsize=100)
    transcribe_queue = Queue(maxsize=2)  # Optimized: reduced buffering for lower latency
    display_queue = Queue(maxsize=10)

    # Components
    capture = AudioCapture(audio_queue, audio_config)
    vad = VADProcessor(audio_queue, transcribe_queue, audio_config, vad_config)
    transcriber = Transcriber(transcribe_queue, display_queue, stt_config)

    # Worker threads
    vad_thread = threading.Thread(target=vad.run, daemon=True, name="VAD")
    stt_thread = threading.Thread(target=transcriber.run, daemon=True, name="STT")

    print("[Benji] Starting...")
    vad_thread.start()
    stt_thread.start()
    capture.start()

    # UI on main thread
    app = QApplication(sys.argv)
    app.setApplicationName("Benji")

    # Install exception hooks to prevent crashes from Qt callbacks
    def qt_exception_hook(exc_type, exc_value, exc_traceback):
        """Catch exceptions in Qt callbacks to prevent abort()."""
        if not issubclass(exc_type, KeyboardInterrupt):
            print(f"[Error] Uncaught exception: {exc_type.__name__}: {exc_value}")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    def unraisable_hook(unraisable):
        """Catch unraisable exceptions (like in Qt callbacks)."""
        print(f"[Error] Unraisable exception: {unraisable.exc_type.__name__}: {unraisable.exc_value}")
        print(f"       in object: {unraisable.object}")

    sys.excepthook = qt_exception_hook
    sys.unraisablehook = unraisable_hook

    overlay = SubtitleOverlay(display_queue, ui_config)

    # History window (initially hidden)
    history_window = HistoryWindow()
    history_window.hide()

    # Global shortcut to show history: Cmd+Shift+H (macOS) or Ctrl+Shift+H (others)
    history_shortcut = QShortcut(QKeySequence("Ctrl+Shift+H"), overlay)
    history_shortcut.activated.connect(lambda: history_window.show() if history_window.isHidden() else history_window.hide())

    # Clean shutdown: stop timers immediately when quit is requested
    app.aboutToQuit.connect(lambda: overlay.cleanup() if not overlay._shutting_down else None)

    # Handle system signals (Ctrl+C, termination)
    def signal_handler(sig, frame):
        """Handle system signals for clean shutdown."""
        print("\n[Benji] Interrupt received, shutting down...")
        overlay.cleanup()
        QTimer.singleShot(0, app.quit)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("[Benji] Press Ctrl+Shift+H to view history")

    exit_code = app.exec()

    # Cleanup
    print("[Benji] Shutting down...")
    capture.stop()
    audio_queue.put(None)
    transcribe_queue.put(None)
    vad_thread.join(timeout=2)
    stt_thread.join(timeout=2)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
