import platform
from queue import Queue, Empty

from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont

from benji.config import UIConfig


class SubtitleOverlay(QWidget):
    new_text_signal = pyqtSignal(str)

    def __init__(self, display_queue: Queue, config: UIConfig = None):
        super().__init__()
        self.display_queue = display_queue
        self.config = config or UIConfig()

        # Window flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        # Label
        self.label = QLabel("")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setFont(
            QFont(self.config.font_family, self.config.font_size, QFont.Weight.Bold)
        )
        self.label.setStyleSheet(f"""
            QLabel {{
                color: white;
                padding: 12px 24px;
                background-color: rgba(0, 0, 0, {self.config.bg_opacity});
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        # Position
        self._position_window()

        # Opacity animation for fade
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Poll display queue
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_queue)
        self.poll_timer.start(50)

        # Auto-hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._start_fade)

        # Signal connection
        self.new_text_signal.connect(self._update_text)

        self.show()
        self._make_click_through()

    def _position_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.geometry()
        width = int(geom.width() * self.config.window_width_ratio)
        height = 120
        x = (geom.width() - width) // 2
        y = geom.height() - height - self.config.bottom_margin
        self.setGeometry(x, y, width, height)

    def _make_click_through(self):
        if platform.system() != "Darwin":
            return
        try:
            from AppKit import NSApp
            for ns_window in NSApp.windows():
                ns_window.setIgnoresMouseEvents_(True)
                # kCGScreenSaverWindowLevel (1000) floats above fullscreen apps
                ns_window.setLevel_(1000)
                ns_window.setCollectionBehavior_(
                    1 << 0   # canJoinAllSpaces
                    | 1 << 4  # stationary
                    | 1 << 7  # canJoinAllApplications
                    | 1 << 9  # fullScreenAuxiliary
                )
                # Ensure the window is not hidden by Expose/Mission Control
                ns_window.setCanHide_(False)
            print("[UI] Click-through + fullscreen overlay enabled")
        except Exception as e:
            print(f"[UI] Click-through setup failed: {e}")

    @pyqtSlot(str)
    def _update_text(self, text: str):
        self.fade_anim.stop()
        self.setWindowOpacity(1.0)
        self.label.setText(text)
        self.hide_timer.start(self.config.display_duration_ms)

    def _poll_queue(self):
        try:
            text = self.display_queue.get_nowait()
            self.new_text_signal.emit(text)
        except Empty:
            pass

    def _start_fade(self):
        self.fade_anim.setDuration(self.config.fade_duration_ms)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.start()
