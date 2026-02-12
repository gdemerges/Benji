import platform
from queue import Queue, Empty

from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont

from benji.config import UIConfig, IS_MACOS, IS_WINDOWS


class SubtitleOverlay(QWidget):
    new_text_signal = pyqtSignal(str)
    new_word_signal = pyqtSignal(dict)

    def __init__(self, display_queue: Queue, config: UIConfig = None):
        super().__init__()
        self.display_queue = display_queue
        self.config = config or UIConfig()
        self.current_text = []  # For streaming mode
        self._shutting_down = False  # Flag to prevent operations during shutdown

        # Window flags (cross-platform)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if IS_MACOS:
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

        # Poll display queue at 60 FPS for smooth updates
        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_queue)
        self.poll_timer.start(16)  # Optimized: ~60 FPS (16ms) vs 20 FPS (50ms)

        # Auto-hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._start_fade)

        # Signal connections
        self.new_text_signal.connect(self._update_text)
        self.new_word_signal.connect(self._update_word)

        self.show()
        self._make_click_through()

    def closeEvent(self, event):
        """Handle window close event - cleanup before Qt destroys objects."""
        self.cleanup()
        event.accept()

    def _position_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        width = int(geom.width() * self.config.window_width_ratio)
        height = 120
        x = geom.x() + (geom.width() - width) // 2
        y = geom.y() + geom.height() - height - self.config.bottom_margin
        self.setGeometry(x, y, width, height)

    def _make_click_through(self):
        if IS_MACOS:
            self._click_through_macos()
        elif IS_WINDOWS:
            self._click_through_windows()

    def _click_through_macos(self):
        try:
            import ctypes
            import ctypes.util
            from AppKit import NSApp

            # Load CoreGraphics
            cg_path = ctypes.util.find_library("CoreGraphics")
            if not cg_path:
                print("[UI] CoreGraphics not found")
                return
            cg = ctypes.CDLL(cg_path)

            # CGWindowLevel constants
            kCGMaximumWindowLevelKey = ctypes.c_int(13)
            CGShieldingWindowLevel = cg.CGShieldingWindowLevel
            CGShieldingWindowLevel.restype = ctypes.c_int32

            max_level = CGShieldingWindowLevel()

            for ns_window in NSApp.windows():
                ns_window.setIgnoresMouseEvents_(True)
                # Use maximum window level to float above fullscreen
                ns_window.setLevel_(max_level)
                ns_window.setCollectionBehavior_(
                    1 << 0   # canJoinAllSpaces
                    | 1 << 4  # stationary
                    | 1 << 7  # canJoinAllApplications
                    | 1 << 9  # fullScreenAuxiliary
                )
                ns_window.setCanHide_(False)
            print(f"[UI] Click-through enabled (macOS, level={max_level})")
        except Exception as e:
            print(f"[UI] macOS click-through failed: {e}")

    def _click_through_windows(self):
        try:
            import win32gui
            import win32con
            hwnd = int(self.winId())
            # Add layered + transparent + tool window extended styles
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= (
                win32con.WS_EX_LAYERED
                | win32con.WS_EX_TRANSPARENT
                | win32con.WS_EX_TOOLWINDOW
                | win32con.WS_EX_TOPMOST
                | win32con.WS_EX_NOACTIVATE
            )
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
            # Force topmost position
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
            )
            print("[UI] Click-through enabled (Windows)")
        except Exception as e:
            print(f"[UI] Windows click-through failed: {e}")

    @pyqtSlot(str)
    def _update_text(self, text: str):
        """Classic mode: replace all text at once."""
        if self._shutting_down:
            return
        try:
            self.fade_anim.stop()
            self.setWindowOpacity(1.0)
            self.label.setText(text)
            self.hide_timer.start(self.config.display_duration_ms)
        except Exception as e:
            if not self._shutting_down:
                print(f"[UI] Error in _update_text: {e}")

    @pyqtSlot(dict)
    def _update_word(self, message: dict):
        """Streaming mode: add words progressively."""
        if self._shutting_down:
            return
        try:
            msg_type = message.get("type")

            if msg_type == "segment_start":
                # Clear previous text
                self.current_text = []
                self.label.setText("")
            elif msg_type == "word":
                # Add new word
                self.current_text.append(message["text"])
                full_text = " ".join(self.current_text)
                self.label.setText(full_text)

            # Reset fade timer and opacity
            self.fade_anim.stop()
            self.setWindowOpacity(1.0)
            self.hide_timer.start(self.config.display_duration_ms)
        except Exception as e:
            if not self._shutting_down:
                print(f"[UI] Error in _update_word: {e}")

    def _poll_queue(self):
        if self._shutting_down:
            return
        try:
            item = self.display_queue.get_nowait()
            # Ignore None (shutdown signal from threads)
            if item is None:
                return
            # Check if streaming message (dict) or classic (str)
            if isinstance(item, dict):
                self.new_word_signal.emit(item)
            elif isinstance(item, str):
                self.new_text_signal.emit(item)
        except Empty:
            pass
        except Exception as e:
            # Prevent crashes from exceptions in Qt callbacks
            if not self._shutting_down:
                print(f"[UI] Error in poll_queue: {e}")

    def _start_fade(self):
        if self._shutting_down:
            return
        try:
            self.fade_anim.setDuration(self.config.fade_duration_ms)
            self.fade_anim.setStartValue(1.0)
            self.fade_anim.setEndValue(0.0)
            self.fade_anim.start()
        except Exception as e:
            if not self._shutting_down:
                print(f"[UI] Error in _start_fade: {e}")

    def cleanup(self):
        """Stop all timers and animations before shutdown."""
        self._shutting_down = True
        self.poll_timer.stop()
        self.hide_timer.stop()
        self.fade_anim.stop()
        # Disconnect signals to prevent any pending emissions
        try:
            self.new_text_signal.disconnect()
            self.new_word_signal.disconnect()
        except:
            pass
