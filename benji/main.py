import sys
import threading
from queue import Queue

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QShortcut, QKeySequence

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
    transcribe_queue = Queue(maxsize=5)
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
    overlay = SubtitleOverlay(display_queue, ui_config)

    # History window (initially hidden)
    history_window = HistoryWindow()
    history_window.hide()

    # Global shortcut to show history: Cmd+Shift+H (macOS) or Ctrl+Shift+H (others)
    history_shortcut = QShortcut(QKeySequence("Ctrl+Shift+H"), overlay)
    history_shortcut.activated.connect(lambda: history_window.show() if history_window.isHidden() else history_window.hide())

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
