import logging

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from benji.config import IS_MACOS, IS_WINDOWS, UIConfig
from benji.ui.style import speaker_color

log = logging.getLogger(__name__)


class VADIndicator(QWidget):
    """Visual indicator for VAD status (speaking/silent)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_speaking = False
        self.setFixedSize(12, 12)

    def set_speaking(self, speaking: bool):
        self.is_speaking = speaking
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw circle
        color = QColor(0, 255, 0, 200) if self.is_speaking else QColor(128, 128, 128, 100)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 12, 12)


class SubtitleOverlay(QWidget):
    new_text_signal = pyqtSignal(str)
    new_word_signal = pyqtSignal(dict)
    vad_status_signal = pyqtSignal(bool)

    def __init__(self, bus, config: UIConfig = None, on_click=None, interactive: bool = False):
        """bus: DisplayBus. on_click: callable() appelé sur mousePressEvent (mode .app).
        interactive: if True, the overlay accepts mouse clicks (needed when on_click
        is bound to bring back the main window). Default False = click-through.
        """
        super().__init__()
        self._bus = bus
        self._on_click = on_click
        self._interactive = interactive
        self.setWindowTitle("BenjiOverlay")
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

        # VAD indicator
        self.vad_indicator = VADIndicator()

        # Label
        self.label = QLabel("")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        self._apply_label_style()

        # Ombre portée douce : donne au bloc sous-titres un rendu « carte
        # flottante » et le détache d'un fond clair. Les marges du layout
        # ci-dessous réservent la place pour que le flou ne soit pas rogné.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 3)
        self.label.setGraphicsEffect(shadow)

        # Layout with VAD indicator
        indicator_layout = QHBoxLayout()
        indicator_layout.addStretch()
        indicator_layout.addWidget(self.vad_indicator)
        indicator_layout.setContentsMargins(8, 8, 20, 0)

        main_layout = QVBoxLayout()
        main_layout.addLayout(indicator_layout)
        main_layout.addWidget(self.label)
        main_layout.setContentsMargins(20, 0, 20, 18)
        main_layout.setSpacing(4)
        self.setLayout(main_layout)

        # Position
        self._position_window()

        # Opacity animation for fade
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Subscribe to display bus events
        bus.event.connect(self._dispatch_event)

        # Auto-hide timer
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._start_fade)

        # Signal connections
        self.new_text_signal.connect(self._update_text)
        self.new_word_signal.connect(self._update_word)
        self.vad_status_signal.connect(self._update_vad_status)

        self.show()
        self._make_click_through()

    @pyqtSlot(bool)
    def _update_vad_status(self, speaking: bool):
        """Update VAD indicator."""
        if self._shutting_down:
            return
        try:
            self.vad_indicator.set_speaking(speaking)
        except Exception:
            if not self._shutting_down:
                log.exception("Error in _update_vad_status")

    def closeEvent(self, event):
        """Handle window close event - cleanup before Qt destroys objects."""
        self.cleanup()
        event.accept()

    def _apply_label_style(self):
        """(Re)applique police + fond depuis self.config au label de sous-titres."""
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

    def apply_config(self, config: UIConfig):
        """Applique à chaud une nouvelle UIConfig (police, opacité, durée, position).

        Appelé depuis le panneau Préférences pour les réglages « live » — pas de
        redémarrage. `display_duration_ms`/`fade_duration_ms` sont lus au vol lors
        des prochains démarrages de timer, donc réassigner self.config suffit.
        """
        if self._shutting_down:
            return
        self.config = config
        self._apply_label_style()
        self._position_window()

    def _position_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        width = int(geom.width() * self.config.window_width_ratio)
        x = geom.x() + (geom.width() - width) // 2
        self.setFixedWidth(width)
        self.setMaximumHeight(int(geom.height() * 0.4))  # Max 40% of screen height
        self.adjustSize()
        y = geom.y() + geom.height() - self.height() - self.config.bottom_margin
        self.move(x, y)

    def _reposition(self):
        """Reanchor window to bottom margin after content height changes."""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        self.adjustSize()
        y = geom.y() + geom.height() - self.height() - self.config.bottom_margin
        self.move(self.x(), y)

    def _make_click_through(self):
        if IS_MACOS:
            self._click_through_macos()
        elif IS_WINDOWS:
            self._click_through_windows()

    def _apply_macos_window_settings(self, verbose: bool = False):
        """(Re)apply window level + collection behavior + private sticky tag.

        Also forces activation policy to Accessory each time, because Qt can
        reset it to Regular on certain events.
        """
        try:
            import ctypes
            import ctypes.util

            from AppKit import NSApp, NSApplicationActivationPolicyAccessory

            # Re-force Accessory policy (Qt may reset to Regular)
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            current_policy = int(NSApp.activationPolicy())

            cg_path = ctypes.util.find_library("CoreGraphics")
            cg = ctypes.CDLL(cg_path)
            cg.CGShieldingWindowLevel.restype = ctypes.c_int32
            max_level = cg.CGShieldingWindowLevel()

            # Private SkyLight/CGS API for sticky-across-fullscreen windows.
            # Tag 0x400 = Sticky. May be restricted on macOS 15+ (Sequoia/Tahoe).
            sticky_ok = False
            conn_id = 0
            try:
                cg.CGSMainConnectionID.restype = ctypes.c_uint32
                conn_id = cg.CGSMainConnectionID()
                cg.CGSSetWindowTags.argtypes = [
                    ctypes.c_uint32,
                    ctypes.c_uint32,
                    ctypes.POINTER(ctypes.c_uint32),
                    ctypes.c_int,
                ]
                cg.CGSSetWindowTags.restype = ctypes.c_int
                sticky_ok = True
            except Exception as e:
                if verbose:
                    log.debug("CGS private API unavailable: %s", e)

            window_debug = []
            for ns_window in NSApp.windows():
                # Only style the overlay's own NSWindow — otherwise we'd float the
                # main app window above everything too, and break its mouse events.
                if ns_window.title() != "BenjiOverlay":
                    continue
                if not self._interactive:
                    ns_window.setIgnoresMouseEvents_(True)
                else:
                    ns_window.setIgnoresMouseEvents_(False)
                ns_window.setLevel_(max_level)
                ns_window.setCollectionBehavior_(
                    (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8)
                )
                ns_window.setCanHide_(False)
                ns_window.setHidesOnDeactivate_(False)
                ns_window.setOpaque_(False)

                tag_result = None
                if sticky_ok:
                    try:
                        wid = int(ns_window.windowNumber())
                        if wid > 0:
                            tags = (ctypes.c_uint32 * 2)(0x00000400, 0x00000000)
                            tag_result = cg.CGSSetWindowTags(conn_id, wid, tags, 32)
                    except Exception as e:
                        tag_result = f"err:{e}"

                if verbose:
                    window_debug.append({
                        "wid": int(ns_window.windowNumber()),
                        "level": int(ns_window.level()),
                        "collection": int(ns_window.collectionBehavior()),
                        "visible": bool(ns_window.isVisible()),
                        "sticky_tag": tag_result,
                    })

            if verbose:
                log.debug("policy=%s (1=Accessory, 0=Regular)", current_policy)
                log.debug("max_level=%s, cgs_conn=%s", max_level, conn_id)
                for w in window_debug:
                    log.debug("window %s", w)
            return max_level
        except Exception as e:
            log.warning("macOS window settings failed: %s", e)
            return None

    def _click_through_macos(self):
        try:
            from AppKit import (
                NSApp,
                NSApplicationActivationPolicyAccessory,
            )

            # Make the process an "accessory" app: no dock icon, behaves like
            # a menu-bar agent, and — crucially — allowed to float over
            # other apps' native fullscreen Spaces.
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

            level = self._apply_macos_window_settings(verbose=True)

            # Re-assert settings when the active Space changes (entering/leaving
            # another app's fullscreen). macOS resets window level on Space change.
            try:
                class _SpaceObserver:
                    def __init__(self, cb):
                        self.cb = cb

                    def spaceDidChange_(self, _notification):
                        self.cb()

                # Keep a strong reference so PyObjC doesn't GC the observer
                self._space_observer = _SpaceObserver(self._apply_macos_window_settings)
                # Fallback: also re-apply on a timer (cheap, ~500ms)
                from PyQt6.QtCore import QTimer
                self._reassert_timer = QTimer(self)
                self._reassert_timer.timeout.connect(self._apply_macos_window_settings)
                self._reassert_timer.start(500)

                # Verbose diagnostic dump every 5s
                self._debug_timer = QTimer(self)
                self._debug_timer.timeout.connect(
                    lambda: self._apply_macos_window_settings(verbose=True)
                )
                self._debug_timer.start(5000)
            except Exception as e:
                log.warning("Space-change observer not installed: %s", e)

            log.info("Click-through enabled (macOS, level=%s, policy=Accessory)", level)
        except Exception as e:
            log.warning("macOS click-through failed: %s", e)

    def _click_through_windows(self):
        try:
            import win32con
            import win32gui
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
            log.info("Click-through enabled (Windows)")
        except Exception as e:
            log.warning("Windows click-through failed: %s", e)

    @pyqtSlot(str)
    def _update_text(self, text: str):
        """Classic mode: replace all text at once."""
        if self._shutting_down:
            return
        try:
            self.fade_anim.stop()
            self.setWindowOpacity(1.0)
            self.label.setText(text)
            self._reposition()
            self.hide_timer.start(self.config.display_duration_ms)
        except Exception:
            if not self._shutting_down:
                log.exception("Error in _update_text")

    @pyqtSlot(dict)
    def _update_word(self, message: dict):
        """Streaming mode: add words progressively."""
        if self._shutting_down:
            return
        try:
            msg_type = message.get("type")

            if msg_type == "segment_start":
                # Reset internal buffer but keep label visible until first word arrives
                self.current_text = []
            elif msg_type == "word":
                # Add new word
                self.current_text.append(message["text"])
                full_text = " ".join(self.current_text)
                self.label.setTextFormat(Qt.TextFormat.PlainText)
                self.label.setText(full_text)
                self._reposition()
                # Reset fade timer only when actual words arrive, not on segment_start
                # This lets the previous text remain visible while the model transcribes
                self.fade_anim.stop()
                self.setWindowOpacity(1.0)
                self.hide_timer.start(self.config.display_duration_ms)
            elif msg_type == "final_text":
                # Replace the streamed (raw) text with the post-processed/corrected
                # final version. If `drop` is set, the segment was a hallucination —
                # clear the overlay immediately instead of leaving garbage on screen.
                if message.get("drop"):
                    self.current_text = []
                    self.label.setText("")
                    self.fade_anim.stop()
                    self.setWindowOpacity(0.0)
                    return
                text = message.get("text") or ""
                self.current_text = text.split() if text else []
                speaker = message.get("speaker")
                if speaker:
                    # Colored speaker prefix; escape the body so stray <,&,> in the
                    # transcription aren't interpreted as markup.
                    from html import escape
                    c = speaker_color(speaker)
                    self.label.setTextFormat(Qt.TextFormat.RichText)
                    self.label.setText(
                        f'<span style="color:{c.name()};font-weight:bold;">{escape(speaker)}</span> '
                        f"{escape(text)}"
                    )
                else:
                    self.label.setTextFormat(Qt.TextFormat.PlainText)
                    self.label.setText(text)
                self._reposition()
                self.fade_anim.stop()
                self.setWindowOpacity(1.0)
                self.hide_timer.start(self.config.display_duration_ms)
        except Exception:
            if not self._shutting_down:
                log.exception("Error in _update_word")

    def _dispatch_event(self, item) -> None:
        if self._shutting_down:
            return
        try:
            if isinstance(item, dict):
                msg_type = item.get("type")
                if msg_type == "vad_status":
                    self.vad_status_signal.emit(item["speaking"])
                else:
                    self.new_word_signal.emit(item)
            elif isinstance(item, str):
                self.new_text_signal.emit(item)
        except Exception:
            if not self._shutting_down:
                log.exception("Error in _dispatch_event")

    def mousePressEvent(self, event):
        if self._on_click is not None:
            try:
                self._on_click()
            except Exception:
                log.exception("Overlay on_click handler raised")
        super().mousePressEvent(event)

    def _start_fade(self):
        if self._shutting_down:
            return
        try:
            self.fade_anim.setDuration(self.config.fade_duration_ms)
            self.fade_anim.setStartValue(1.0)
            self.fade_anim.setEndValue(0.0)
            self.fade_anim.start()
        except Exception:
            if not self._shutting_down:
                log.exception("Error in _start_fade")

    def cleanup(self):
        """Stop all timers and animations before shutdown."""
        self._shutting_down = True
        self.hide_timer.stop()
        self.fade_anim.stop()
        if hasattr(self, "_reassert_timer"):
            self._reassert_timer.stop()
        if hasattr(self, "_debug_timer"):
            self._debug_timer.stop()
        # Disconnect signals to prevent any pending emissions
        try:
            self.new_text_signal.disconnect()
            self.new_word_signal.disconnect()
        except:
            pass
