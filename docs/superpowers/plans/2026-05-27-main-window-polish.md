# Polish esthétique fenêtre principale — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Donner à la fenêtre principale un look macOS natif raffiné (vibrancy, palette système, SF Pro, segmented control, status pill animé, chat-log retravaillé, liste de résumés groupée par jour) sans modifier la structure ni les comportements.

**Architecture:** Un module central `benji/ui/style.py` expose un `Theme` adaptatif (light/dark) + un helper de vibrancy macOS via PyObjC. Les écrans (`MainWindow`, `LiveTab`, `SummariesTab`) consomment le thème et sont refactorés pour utiliser des widgets custom (`StatusPill`, `SegmentedControl`, `ChatItem`, `PartialBubble`, `SummaryItem`, `PendingItem`) au lieu des contrôles Qt génériques. Tous les widgets se rebuildent au changement de thème système.

**Tech Stack:** PyQt6, PyObjC (`pyobjc-framework-Cocoa`), Python 3.12, `uv`.

**Spec:** `docs/superpowers/specs/2026-05-27-main-window-polish-design.md`

**Note sur les tests :** ce plan est principalement visuel ; pas de TDD strict. Chaque tâche se termine par un smoke check `uv run benji` à l'œil. Les tests automatisés se limitent à de l'import + instanciation pour détecter les régressions de chargement.

---

## File Structure

**Created :**
- `benji/ui/style.py` — palette adaptive, vibrancy macOS, helpers couleurs/QSS
- `benji/ui/widgets/__init__.py` — package widgets custom
- `benji/ui/widgets/status_pill.py` — pill statut VAD + timer
- `benji/ui/widgets/segmented_control.py` — segmented control style macOS
- `benji/ui/widgets/chat_item.py` — item ligne du chat-log Live
- `benji/ui/widgets/partial_bubble.py` — carte partiel avec curseur clignotant
- `benji/ui/widgets/summary_item.py` — item liste résumés
- `benji/ui/widgets/pending_item.py` — item résumé en cours
- `benji/ui/widgets/icons.py` — SVG inline → QIcon
- `tests/ui/test_main_window_smoke.py` — smoke test instanciation

**Modified :**
- `benji/ui/main_window.py` — vibrancy, theme listener, StatusPill, SegmentedControl, boutons stylés
- `benji/ui/live_tab.py` — QScrollArea + ChatItem + PartialBubble (refonte du rendu)
- `benji/ui/summaries_tab.py` — items custom, groupage par jour, preview stylée, PendingItem
- `benji/ui/CLAUDE.md` — documenter les nouveaux modules

---

## Task 1: Module `style.py` — palette et thème adaptatif

**Files:**
- Create: `benji/ui/style.py`

- [ ] **Step 1: Créer le squelette du module**

```python
"""Palette adaptive, helpers QSS et vibrancy macOS pour la fenêtre principale."""

from __future__ import annotations

import logging
import platform
from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QPalette
from PyQt6.QtWidgets import QApplication, QWidget

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Theme:
    is_dark: bool
    label: QColor
    secondary_label: QColor
    tertiary_label: QColor
    quaternary_label: QColor
    accent: QColor
    live_red: QColor
    window_background: QColor
    separator: QColor

    def accent_alpha(self, pct: int) -> QColor:
        c = QColor(self.accent)
        c.setAlpha(int(255 * pct / 100))
        return c

    def label_alpha(self, pct: int) -> QColor:
        c = QColor(self.label)
        c.setAlpha(int(255 * pct / 100))
        return c


def _is_dark() -> bool:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        return False


def current_theme() -> Theme:
    dark = _is_dark()
    if dark:
        return Theme(
            is_dark=True,
            label=QColor(255, 255, 255, 230),
            secondary_label=QColor(255, 255, 255, 153),
            tertiary_label=QColor(255, 255, 255, 102),
            quaternary_label=QColor(255, 255, 255, 51),
            accent=QApplication.palette().color(QPalette.ColorRole.Highlight),
            live_red=QColor("#FF453A"),
            window_background=QColor(30, 30, 30),
            separator=QColor(255, 255, 255, 38),
        )
    return Theme(
        is_dark=False,
        label=QColor(0, 0, 0, 217),
        secondary_label=QColor(0, 0, 0, 153),
        tertiary_label=QColor(0, 0, 0, 102),
        quaternary_label=QColor(0, 0, 0, 38),
        accent=QApplication.palette().color(QPalette.ColorRole.Highlight),
        live_red=QColor("#FF3B30"),
        window_background=QColor(246, 246, 246),
        separator=QColor(0, 0, 0, 25),
    )


def install_theme_listener(callback: Callable[[], None]) -> None:
    """Appelle `callback` chaque fois que le système bascule light/dark."""
    QGuiApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: callback())


# Font stacks
FONT_UI = '"-apple-system", "SF Pro Text", system-ui, sans-serif'
FONT_DISPLAY = '"-apple-system", "SF Pro Display", "SF Pro Text", system-ui, sans-serif'
FONT_MONO = '"SF Mono", Menlo, monospace'
```

- [ ] **Step 2: Ajouter `apply_window_vibrancy()` (no-op hors macOS pour l'instant)**

À la fin de `benji/ui/style.py` :

```python
def apply_window_vibrancy(window: QWidget) -> None:
    """macOS : NSVisualEffectView material underWindowBackground. No-op ailleurs."""
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import (
            NSVisualEffectView,
            NSVisualEffectMaterialUnderWindowBackground,
            NSVisualEffectBlendingModeBehindWindow,
            NSVisualEffectStateActive,
        )
        import objc
        from objc import objc_object

        # Récupère la NSView racine depuis le winId de la QWidget
        view_ptr = int(window.winId())
        ns_view = objc_object(c_void_p=view_ptr)
        ns_window = ns_view.window()
        content = ns_window.contentView()

        effect = NSVisualEffectView.alloc().initWithFrame_(content.bounds())
        effect.setAutoresizingMask_(18)  # NSViewWidthSizable | NSViewHeightSizable
        effect.setMaterial_(NSVisualEffectMaterialUnderWindowBackground)
        effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        effect.setState_(NSVisualEffectStateActive)
        content.addSubview_positioned_relativeTo_(effect, -1, None)  # NSWindowBelow

        ns_window.setOpaque_(False)
        ns_window.setBackgroundColor_(
            __import__("AppKit").NSColor.clearColor()
        )
        log.info("macOS vibrancy applied")
    except Exception as e:
        log.warning("vibrancy failed: %s", e)
```

- [ ] **Step 3: Smoke import**

Run: `uv run python -c "from benji.ui.style import current_theme, apply_window_vibrancy, install_theme_listener; print(current_theme())"`
Expected: pas d'erreur, ligne `Theme(is_dark=...)` affichée.

- [ ] **Step 4: Commit**

```bash
git add benji/ui/style.py
git commit -m "feat(ui): module style — thème adaptive + vibrancy macOS"
```

---

## Task 2: Package `widgets/` + module icons

**Files:**
- Create: `benji/ui/widgets/__init__.py`
- Create: `benji/ui/widgets/icons.py`

- [ ] **Step 1: Créer `benji/ui/widgets/__init__.py` vide**

```python
"""Widgets custom pour la fenêtre principale."""
```

- [ ] **Step 2: Créer `benji/ui/widgets/icons.py`**

```python
"""SVG inline → QIcon. Couleur adaptée au thème courant."""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_DOC_TEXT = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <path d='M6 3h9l4 4v14a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z'
        fill='none' stroke='COLOR' stroke-width='1.6' stroke-linejoin='round'/>
  <path d='M14 3v5h5' fill='none' stroke='COLOR' stroke-width='1.6'/>
  <path d='M8 13h8M8 16h8M8 10h4' stroke='COLOR' stroke-width='1.4' stroke-linecap='round'/>
</svg>
"""

_MINIMIZE = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <path d='M14 4h6v6M20 4l-7 7M10 20H4v-6M4 20l7-7'
        fill='none' stroke='COLOR' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/>
</svg>
"""

_CLIPBOARD = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <rect x='6' y='4' width='12' height='17' rx='2' fill='none' stroke='COLOR' stroke-width='1.6'/>
  <rect x='9' y='2' width='6' height='4' rx='1' fill='COLOR' opacity='0.15' stroke='COLOR' stroke-width='1.6'/>
</svg>
"""

_FOLDER_ARROW = """
<svg viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'>
  <path d='M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z'
        fill='none' stroke='COLOR' stroke-width='1.6' stroke-linejoin='round'/>
  <path d='M11 14l3-3-3-3M14 11H8' fill='none' stroke='COLOR' stroke-width='1.6' stroke-linecap='round'/>
</svg>
"""


def _render(svg: str, color_hex: str, size: int = 18) -> QIcon:
    data = svg.replace("COLOR", color_hex).encode("utf-8")
    renderer = QSvgRenderer(QByteArray(data))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    renderer.render(p)
    p.end()
    return QIcon(pixmap)


def doc_text_icon(color_hex: str) -> QIcon:
    return _render(_DOC_TEXT, color_hex)


def minimize_icon(color_hex: str) -> QIcon:
    return _render(_MINIMIZE, color_hex)


def clipboard_icon(color_hex: str) -> QIcon:
    return _render(_CLIPBOARD, color_hex)


def folder_arrow_icon(color_hex: str) -> QIcon:
    return _render(_FOLDER_ARROW, color_hex)
```

- [ ] **Step 3: Vérifier l'import**

Run: `uv run python -c "from benji.ui.widgets.icons import doc_text_icon; print(doc_text_icon('#ffffff'))"`
Expected: pas d'erreur, ligne `<PyQt6.QtGui.QIcon object at ...>`.

- [ ] **Step 4: Commit**

```bash
git add benji/ui/widgets/__init__.py benji/ui/widgets/icons.py
git commit -m "feat(ui): widgets package + icons SVG inline"
```

---

## Task 3: `StatusPill` — indicateur VAD + timer session

**Files:**
- Create: `benji/ui/widgets/status_pill.py`

- [ ] **Step 1: Créer le widget**

```python
"""Pill statut : dot pulsant + label + timer session."""

from __future__ import annotations

from datetime import datetime, timedelta

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty,
)
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from benji.ui.style import current_theme, FONT_UI, FONT_MONO


class _PulseDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = QColor(150, 150, 150)
        self._opacity = 1.0
        self._anim = QPropertyAnimation(self, b"opacity_prop")
        self._anim.setDuration(1200)
        self._anim.setStartValue(1.0)
        self._anim.setKeyValueAt(0.5, 0.35)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._anim.setLoopCount(-1)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def set_pulsing(self, on: bool) -> None:
        if on:
            self._anim.start()
        else:
            self._anim.stop()
            self._opacity = 1.0
            self.update()

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, v: float) -> None:
        self._opacity = v
        self.update()

    opacity_prop = pyqtProperty(float, fget=_get_opacity, fset=_set_opacity)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(self._opacity)
        p.setBrush(c)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 8, 8)


class StatusPill(QWidget):
    def __init__(self, session_start: datetime, parent=None):
        super().__init__(parent)
        self._session_start = session_start
        self._speaking = False

        self.dot = _PulseDot(self)
        self.status_label = QLabel("En attente")
        self.sep_label = QLabel(" · ")
        self.timer_label = QLabel("00:00")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 12, 4)
        layout.setSpacing(6)
        layout.addWidget(self.dot)
        layout.addSpacing(2)
        layout.addWidget(self.status_label)
        layout.addWidget(self.sep_label)
        layout.addWidget(self.timer_label)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(1000)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start()

        self.apply_theme()

    def apply_theme(self) -> None:
        t = current_theme()
        bg = t.label_alpha(6) if t.is_dark else t.label_alpha(5)
        self.setStyleSheet(f"""
            StatusPill {{
                background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});
                border-radius: 11px;
            }}
            QLabel {{
                font-family: {FONT_UI};
                font-size: 12px;
                color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()});
                background: transparent;
            }}
        """)
        # Mono pour le timer
        self.timer_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 12px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent;"
        )
        self._refresh_dot_color()

    def set_speaking(self, speaking: bool) -> None:
        if speaking == self._speaking:
            return
        self._speaking = speaking
        self.status_label.setText("En écoute" if speaking else "En attente")
        self._refresh_dot_color()
        self.dot.set_pulsing(speaking)

    def _refresh_dot_color(self) -> None:
        t = current_theme()
        self.dot.set_color(t.live_red if self._speaking else t.tertiary_label)

    def _tick(self) -> None:
        delta: timedelta = datetime.now() - self._session_start
        total = int(delta.total_seconds())
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        self.timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")
```

- [ ] **Step 2: Smoke test**

Run: `uv run python -c "from PyQt6.QtWidgets import QApplication; import sys; app = QApplication(sys.argv); from datetime import datetime; from benji.ui.widgets.status_pill import StatusPill; w = StatusPill(datetime.now()); w.show(); from PyQt6.QtCore import QTimer; QTimer.singleShot(300, app.quit); app.exec()"`
Expected: la fenêtre apparaît brièvement (300ms) puis quitte sans erreur.

- [ ] **Step 3: Commit**

```bash
git add benji/ui/widgets/status_pill.py
git commit -m "feat(ui): StatusPill — dot pulsant + timer session"
```

---

## Task 4: `SegmentedControl` — onglets style macOS

**Files:**
- Create: `benji/ui/widgets/segmented_control.py`

- [ ] **Step 1: Créer le widget**

```python
"""Segmented control style macOS — 2+ segments mutually exclusive."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from benji.ui.style import current_theme, FONT_UI


class SegmentedControl(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._badges: dict[int, bool] = {}
        self._current = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)

        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, idx=i: self.setCurrentIndex(idx))
            layout.addWidget(btn, 1)
            self._buttons.append(btn)

        self.setCurrentIndex(0)
        self.apply_theme()

    def setCurrentIndex(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._buttons):
            return
        for i, b in enumerate(self._buttons):
            b.setChecked(i == idx)
        if idx != self._current:
            self._current = idx
            self.currentChanged.emit(idx)
        self._refresh_labels()

    def currentIndex(self) -> int:
        return self._current

    def setBadge(self, idx: int, has_badge: bool) -> None:
        self._badges[idx] = has_badge
        self._refresh_labels()

    def _refresh_labels(self) -> None:
        # On garde le label de base et on suffixe par "  •" si badge
        base_labels = getattr(self, "_base_labels", None)
        if base_labels is None:
            self._base_labels = [b.text().rstrip(" •").strip() for b in self._buttons]
            base_labels = self._base_labels
        for i, b in enumerate(self._buttons):
            base = base_labels[i]
            b.setText(f"{base}  •" if self._badges.get(i) else base)

    def apply_theme(self) -> None:
        t = current_theme()
        track = t.label_alpha(7)
        active = t.label_alpha(14)
        label = t.label
        secondary = t.secondary_label
        self.setStyleSheet(f"""
            SegmentedControl {{
                background-color: rgba({track.red()},{track.green()},{track.blue()},{track.alpha()});
                border-radius: 8px;
            }}
            QPushButton {{
                font-family: {FONT_UI};
                font-size: 12px;
                font-weight: 500;
                color: rgba({secondary.red()},{secondary.green()},{secondary.blue()},{secondary.alpha()});
                background: transparent;
                border: none;
                padding: 4px 14px;
                border-radius: 6px;
            }}
            QPushButton:checked {{
                background-color: rgba({active.red()},{active.green()},{active.blue()},{active.alpha()});
                color: rgba({label.red()},{label.green()},{label.blue()},{label.alpha()});
            }}
            QPushButton:hover:!checked {{
                color: rgba({label.red()},{label.green()},{label.blue()},{label.alpha()});
            }}
        """)
        self.setFixedHeight(30)
```

- [ ] **Step 2: Commit**

```bash
git add benji/ui/widgets/segmented_control.py
git commit -m "feat(ui): SegmentedControl style macOS"
```

---

## Task 5: Intégrer vibrancy + StatusPill + SegmentedControl dans `MainWindow`

**Files:**
- Modify: `benji/ui/main_window.py`

- [ ] **Step 1: Remplacer intégralement `benji/ui/main_window.py`**

```python
"""Fenêtre principale : toolbar + onglets Live/Résumés (style macOS natif)."""

from __future__ import annotations

import logging
import platform
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow, QPushButton, QSizePolicy, QStackedWidget,
    QToolBar, QVBoxLayout, QWidget,
)

from benji.ui.live_tab import LiveTab
from benji.ui.summaries_tab import SummariesTab
from benji.ui.style import (
    apply_window_vibrancy, current_theme, install_theme_listener,
    FONT_UI,
)
from benji.ui.widgets.icons import doc_text_icon, minimize_icon
from benji.ui.widgets.segmented_control import SegmentedControl
from benji.ui.widgets.status_pill import StatusPill

log = logging.getLogger(__name__)

_SETTINGS_ORG = "benji"
_SETTINGS_APP = "benji"
_GEOM_KEY = "main_window/geometry"
_TAB_KEY = "main_window/tab_index"


class MainWindow(QMainWindow):
    def __init__(
        self,
        bus,
        history,
        session_start: datetime,
        summary_worker,
        on_minimize=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Benji")
        self._bus = bus
        self._history = history
        self._session_start = session_start
        self._worker = summary_worker
        self._on_minimize = on_minimize
        self._pending_summary_id: str | None = None
        self._has_unread_summary = False

        self._build_ui()
        self._wire_worker()
        self._restore_state()

        if platform.system() == "Darwin":
            self.setUnifiedTitleAndToolBarOnMac(True)

        install_theme_listener(self._apply_theme)
        self._apply_theme()

    def showEvent(self, event):
        super().showEvent(event)
        # Vibrancy doit être appliquée après que la NSWindow existe
        if not getattr(self, "_vibrancy_applied", False):
            apply_window_vibrancy(self)
            self._vibrancy_applied = True

    def _build_ui(self) -> None:
        # === Toolbar ===
        tb = QToolBar("main")
        tb.setMovable(False)
        tb.setIconSize(tb.iconSize())
        self.addToolBar(tb)

        self.status_pill = StatusPill(self._session_start)
        tb.addWidget(self.status_pill)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self.summarize_btn = QPushButton("Résumer")
        self.summarize_btn.setObjectName("summarize_btn")
        self.summarize_btn.clicked.connect(self._request_summary)
        tb.addWidget(self.summarize_btn)

        self.minimize_btn = QPushButton("Réduire")
        self.minimize_btn.setObjectName("minimize_btn")
        self.minimize_btn.clicked.connect(self._minimize)
        tb.addWidget(self.minimize_btn)

        # === Central ===
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 8, 0, 0)
        v.setSpacing(8)

        seg_wrap = QHBoxLayout()
        seg_wrap.addStretch(1)
        self.segmented = SegmentedControl(["Live", "Résumés"])
        self.segmented.setFixedWidth(260)
        seg_wrap.addWidget(self.segmented)
        seg_wrap.addStretch(1)
        v.addLayout(seg_wrap)

        self.stack = QStackedWidget()
        self.live_tab = LiveTab()
        self.summaries_tab = SummariesTab()
        self.stack.addWidget(self.live_tab)
        self.stack.addWidget(self.summaries_tab)
        v.addWidget(self.stack, 1)

        self.segmented.currentChanged.connect(self.stack.setCurrentIndex)
        self.segmented.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(central)

        # === Bus wiring ===
        self._bus.event.connect(self.live_tab.on_event)
        self._bus.event.connect(self._update_vad_indicator)
        self._bus.event.connect(self._maybe_refresh_summarize_enabled)

        self._refresh_summarize_enabled()

    def _apply_theme(self) -> None:
        t = current_theme()
        bg = t.window_background
        # Fond de la centrale : transparent (vibrancy passe à travers sur macOS).
        # Hors macOS, on pose un fond opaque.
        if platform.system() == "Darwin":
            self.setStyleSheet(f"""
                QMainWindow {{ background: transparent; }}
                QToolBar {{ background: transparent; border: none; padding: 8px 12px; spacing: 8px; }}
            """)
        else:
            self.setStyleSheet(f"""
                QMainWindow {{ background-color: rgb({bg.red()},{bg.green()},{bg.blue()}); }}
                QToolBar {{ background: transparent; border: none; padding: 8px 12px; spacing: 8px; }}
            """)
        self.status_pill.apply_theme()
        self.segmented.apply_theme()
        self._apply_toolbar_button_styles()
        # Propager aux onglets
        if hasattr(self.live_tab, "apply_theme"):
            self.live_tab.apply_theme()
        if hasattr(self.summaries_tab, "apply_theme"):
            self.summaries_tab.apply_theme()

    def _apply_toolbar_button_styles(self) -> None:
        t = current_theme()
        accent = t.accent
        on_accent = "#ffffff"
        hover = t.label_alpha(8)
        label = t.label
        # Filled accent — "Résumer"
        self.summarize_btn.setIcon(doc_text_icon(on_accent))
        self.summarize_btn.setStyleSheet(f"""
            QPushButton#summarize_btn {{
                font-family: {FONT_UI};
                font-size: 12px;
                font-weight: 500;
                color: {on_accent};
                background-color: rgb({accent.red()},{accent.green()},{accent.blue()});
                border: none;
                padding: 6px 14px;
                border-radius: 6px;
            }}
            QPushButton#summarize_btn:hover {{
                background-color: rgba({accent.red()},{accent.green()},{accent.blue()},220);
            }}
            QPushButton#summarize_btn:disabled {{
                background-color: rgba({accent.red()},{accent.green()},{accent.blue()},90);
                color: rgba(255,255,255,160);
            }}
        """)
        # Ghost — "Réduire"
        self.minimize_btn.setIcon(minimize_icon(f"#{label.red():02x}{label.green():02x}{label.blue():02x}"))
        self.minimize_btn.setStyleSheet(f"""
            QPushButton#minimize_btn {{
                font-family: {FONT_UI};
                font-size: 12px;
                font-weight: 500;
                color: rgba({label.red()},{label.green()},{label.blue()},{label.alpha()});
                background: transparent;
                border: none;
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QPushButton#minimize_btn:hover {{
                background-color: rgba({hover.red()},{hover.green()},{hover.blue()},{hover.alpha()});
            }}
        """)

    def _wire_worker(self) -> None:
        self._worker.started.connect(self._on_summary_started)
        self._worker.chunk.connect(self._on_summary_chunk)
        self._worker.finished.connect(self._on_summary_finished)
        self._worker.failed.connect(self._on_summary_failed)

    def _update_vad_indicator(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "vad_status":
            self.status_pill.set_speaking(bool(item.get("speaking")))

    def _maybe_refresh_summarize_enabled(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "final_text" and item.get("text"):
            self._refresh_summarize_enabled()

    def _refresh_summarize_enabled(self) -> None:
        try:
            has_history = bool(self._history.get_since(self._session_start))
        except Exception:
            has_history = False
        idle = self._pending_summary_id is None
        self.summarize_btn.setEnabled(has_history and idle)

    def _request_summary(self) -> None:
        entries = self._history.get_since(self._session_start)
        if not entries:
            return
        sid = uuid.uuid4().hex
        self._pending_summary_id = sid
        self._refresh_summarize_enabled()
        self.summaries_tab.begin_pending(sid)
        self._refresh_tab_badge()
        self._worker.request(entries=entries, summary_id=sid)

    def _on_summary_started(self, sid: str) -> None:
        log.info("Summary started: %s", sid)

    def _on_summary_chunk(self, sid: str, chunk: str) -> None:
        self.summaries_tab.append_chunk(sid, chunk)

    def _on_summary_finished(self, sid: str, path: Path) -> None:
        self.summaries_tab.finalize_pending(sid, path)
        self._pending_summary_id = None
        self._has_unread_summary = (self.segmented.currentIndex() != 1)
        self._refresh_tab_badge()
        self._refresh_summarize_enabled()

    def _on_summary_failed(self, sid: str, err: str) -> None:
        self.summaries_tab.fail_pending(sid, err)
        self._pending_summary_id = None
        self._refresh_tab_badge()
        self._refresh_summarize_enabled()

    def _on_tab_changed(self, idx: int) -> None:
        if idx == 1:
            self._has_unread_summary = False
            self._refresh_tab_badge()

    def _refresh_tab_badge(self) -> None:
        has_badge = self._pending_summary_id is not None or self._has_unread_summary
        self.segmented.setBadge(1, has_badge)

    def _minimize(self) -> None:
        if self._on_minimize is not None:
            self._on_minimize()

    def _restore_state(self) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        geom = s.value(_GEOM_KEY)
        if geom is not None:
            try:
                self.restoreGeometry(geom)
            except Exception:
                self.resize(960, 640)
        else:
            self.resize(960, 640)
        tab = s.value(_TAB_KEY, 0, type=int)
        self.segmented.setCurrentIndex(tab)
        self.stack.setCurrentIndex(tab)

    def closeEvent(self, event) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue(_GEOM_KEY, self.saveGeometry())
        s.setValue(_TAB_KEY, self.segmented.currentIndex())
        super().closeEvent(event)
```

- [ ] **Step 2: Smoke launch**

Run: `uv run benji`
Expected: la fenêtre principale s'ouvre, status pill visible à gauche avec dot gris + "En attente · 00:00", boutons "Résumer" (filled bleu) + "Réduire" (ghost) à droite, segmented control "Live | Résumés" centré sous la toolbar. Sur macOS, fond translucide visible. Quitter avec ⌘Q.

- [ ] **Step 3: Commit**

```bash
git add benji/ui/main_window.py
git commit -m "feat(ui): main window — vibrancy, StatusPill, SegmentedControl, boutons stylés"
```

---

## Task 6: `ChatItem` + `PartialBubble` widgets

**Files:**
- Create: `benji/ui/widgets/chat_item.py`
- Create: `benji/ui/widgets/partial_bubble.py`

- [ ] **Step 1: Créer `chat_item.py`**

```python
"""Item ligne du chat-log Live : timestamp + texte."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QPropertyAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from benji.ui.style import current_theme, FONT_UI, FONT_MONO


class ChatItem(QWidget):
    def __init__(self, text: str, ts: datetime | None = None, parent=None):
        super().__init__(parent)
        self._text = text
        self._ts = ts or datetime.now()

        self.ts_label = QLabel(self._ts.strftime("%H:%M"))
        self.ts_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.ts_label.setFixedWidth(52)

        self.text_label = QLabel(self._text)
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(14)
        layout.addWidget(self.ts_label, 0)
        layout.addWidget(self.text_label, 1)

        self.apply_theme()
        self._fade_in()

    def apply_theme(self) -> None:
        t = current_theme()
        self.ts_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent; padding-top: 2px;"
        )
        self.text_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 15px; line-height: 1.5; "
            f"color: rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()}); "
            "background: transparent;"
        )

    def _fade_in(self) -> None:
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.0)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._fade_anim = anim
```

- [ ] **Step 2: Créer `partial_bubble.py`**

```python
"""Carte flottante du texte partiel avec curseur clignotant."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from benji.ui.style import current_theme, FONT_UI


class PartialBubble(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._text: str = ""
        self._cursor_on = True

        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.cursor_label = QLabel("▌")
        self.cursor_label.setFixedWidth(8)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(self.text_label, 1)
        layout.addWidget(self.cursor_label, 0, Qt.AlignmentFlag.AlignBottom)

        self._blink = QTimer(self)
        self._blink.setInterval(600)
        self._blink.timeout.connect(self._toggle_cursor)
        self._blink.start()

        self.apply_theme()
        self.setVisible(False)

    def set_text(self, text: str) -> None:
        self._text = text
        self.text_label.setText(text)
        self.setVisible(bool(text))

    def apply_theme(self) -> None:
        t = current_theme()
        bg = t.accent_alpha(10)
        self.setStyleSheet(f"""
            PartialBubble {{
                background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});
                border-radius: 8px;
            }}
        """)
        label_css = (
            f"font-family: {FONT_UI}; font-size: 14px; font-style: italic; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
        self.text_label.setStyleSheet(label_css)
        self.cursor_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 14px; "
            f"color: rgba({t.accent.red()},{t.accent.green()},{t.accent.blue()},{t.accent.alpha()}); "
            "background: transparent;"
        )

    def _toggle_cursor(self) -> None:
        self._cursor_on = not self._cursor_on
        self.cursor_label.setVisible(self._cursor_on)
```

- [ ] **Step 3: Commit**

```bash
git add benji/ui/widgets/chat_item.py benji/ui/widgets/partial_bubble.py
git commit -m "feat(ui): ChatItem + PartialBubble widgets"
```

---

## Task 7: Refonte `LiveTab`

**Files:**
- Modify: `benji/ui/live_tab.py`

- [ ] **Step 1: Remplacer intégralement `benji/ui/live_tab.py`**

```python
"""Onglet 'Live' : chat-log scrollable + bubble partielle."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QScrollArea, QVBoxLayout, QWidget,
)

from benji.ui.style import current_theme
from benji.ui.widgets.chat_item import ChatItem
from benji.ui.widgets.partial_bubble import PartialBubble

_MAX_CONTENT_WIDTH = 720


class LiveTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._partial_text: str = ""
        self._user_scrolled_up = False
        self._build_ui()

    def _build_ui(self) -> None:
        # Scroll area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Container centré largeur max
        self.viewport_widget = QWidget()
        outer = QHBoxLayout(self.viewport_widget)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(0)
        outer.addStretch(1)

        self.content = QWidget()
        self.content.setMaximumWidth(_MAX_CONTENT_WIDTH)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.addStretch(1)
        outer.addWidget(self.content, 0)
        outer.addStretch(1)

        self.scroll.setWidget(self.viewport_widget)

        # Partial bubble (centré, sous le scroll)
        self.partial = PartialBubble()
        partial_wrap = QHBoxLayout()
        partial_wrap.setContentsMargins(20, 0, 20, 14)
        partial_wrap.addStretch(1)
        self.partial.setMaximumWidth(_MAX_CONTENT_WIDTH)
        partial_wrap.addWidget(self.partial, 1)
        partial_wrap.addStretch(1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.scroll, 1)
        root.addLayout(partial_wrap)

        self.apply_theme()

    def apply_theme(self) -> None:
        t = current_theme()
        # Fond transparent pour laisser passer la vibrancy
        self.setStyleSheet("LiveTab, QScrollArea { background: transparent; border: none; }")
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.viewport_widget.setStyleSheet("background: transparent;")
        self.content.setStyleSheet("background: transparent;")
        # Propagation aux items existants
        for i in range(self.content_layout.count() - 1):  # -1 pour le stretch
            w = self.content_layout.itemAt(i).widget()
            if w is not None and hasattr(w, "apply_theme"):
                w.apply_theme()
        self.partial.apply_theme()

    def on_event(self, item) -> None:
        if not isinstance(item, dict):
            return
        msg_type = item.get("type")
        if msg_type == "segment_start":
            self._partial_text = ""
            self.partial.set_text("")
        elif msg_type == "word":
            text = item.get("text", "")
            if not text:
                return
            sep = "" if (not self._partial_text or self._partial_text.endswith(" ") or text.startswith((".", ",", "!", "?", ";", ":"))) else " "
            self._partial_text = (self._partial_text + sep + text).strip()
            self.partial.set_text(self._partial_text)
        elif msg_type == "final_text":
            text = item.get("text", "")
            drop = item.get("drop", False)
            if drop or not text:
                self._partial_text = ""
                self.partial.set_text("")
                return
            self._append_final(text)
            self._partial_text = ""
            self.partial.set_text("")

    def _append_final(self, text: str) -> None:
        item = ChatItem(text)
        # Insère avant le stretch final
        self.content_layout.insertWidget(self.content_layout.count() - 1, item)
        if not self._user_scrolled_up:
            # Defer scroll to next event loop pour laisser le layout se calculer
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_scroll(self, value: int) -> None:
        sb = self.scroll.verticalScrollBar()
        self._user_scrolled_up = (sb.maximum() - value) > 20
```

- [ ] **Step 2: Smoke launch**

Run: `uv run benji`
Expected: l'onglet Live est vide au démarrage, fond translucide. Parler dans le micro : voir le partial bubble apparaître en bas (italique, accent translucide, curseur clignotant), puis quand l'utterance termine, voir un ChatItem (timestamp gris à gauche, texte à droite) apparaître avec fade-in.

- [ ] **Step 3: Commit**

```bash
git add benji/ui/live_tab.py
git commit -m "feat(ui): LiveTab — QScrollArea + ChatItems + PartialBubble"
```

---

## Task 8: `SummaryItem` + `PendingItem` widgets

**Files:**
- Create: `benji/ui/widgets/summary_item.py`
- Create: `benji/ui/widgets/pending_item.py`

- [ ] **Step 1: Créer `summary_item.py`**

```python
"""Item de la liste des résumés."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from benji.ui.style import current_theme, FONT_UI, FONT_MONO


class SummaryItem(QWidget):
    def __init__(self, dt: datetime, snippet: str, parent=None):
        super().__init__(parent)
        self._dt = dt
        self._snippet = snippet

        self.date_label = QLabel(self._format_date(dt))
        self.time_label = QLabel(dt.strftime("%H:%M"))
        self.snippet_label = QLabel(snippet)
        self.snippet_label.setWordWrap(False)
        self.snippet_label.setTextFormat(Qt.TextFormat.PlainText)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self.date_label, 0)
        top.addWidget(self.time_label, 0)
        top.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)
        layout.addLayout(top)
        layout.addWidget(self.snippet_label)

        self.apply_theme()

    @staticmethod
    def _format_date(dt: datetime) -> str:
        return dt.strftime("%d %b").lstrip("0")

    def apply_theme(self) -> None:
        t = current_theme()
        self.date_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 13px; font-weight: 600; "
            f"color: rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()}); "
            "background: transparent;"
        )
        self.time_label.setStyleSheet(
            f"font-family: {FONT_MONO}; font-size: 11px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "background: transparent;"
        )
        self.snippet_label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 12px; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
```

- [ ] **Step 2: Créer `pending_item.py`**

```python
"""Item résumé en cours de génération — spinner pill fin."""

from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from benji.ui.style import current_theme, FONT_UI


class PendingItem(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = QLabel("Génération du résumé…")
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # indeterminate
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(3)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)

        self.apply_theme()

    def apply_theme(self) -> None:
        t = current_theme()
        bg = t.accent_alpha(10)
        self.setStyleSheet(f"""
            PendingItem {{
                background-color: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});
                border-radius: 6px;
            }}
        """)
        self.label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 12px; "
            f"color: rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()}); "
            "background: transparent;"
        )
        track = t.label_alpha(8)
        accent = t.accent
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: rgba({track.red()},{track.green()},{track.blue()},{track.alpha()});
                border: none;
                border-radius: 1px;
            }}
            QProgressBar::chunk {{
                background-color: rgb({accent.red()},{accent.green()},{accent.blue()});
                border-radius: 1px;
            }}
        """)

    def set_failed(self, error: str) -> None:
        t = current_theme()
        red = t.live_red
        self.label.setText(f"Échec — {error[:80]}")
        self.bar.setVisible(False)
        self.setStyleSheet(f"""
            PendingItem {{
                background-color: rgba({red.red()},{red.green()},{red.blue()},25);
                border-radius: 6px;
            }}
        """)
        self.label.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 12px; "
            f"color: rgb({red.red()},{red.green()},{red.blue()}); "
            "background: transparent;"
        )
```

- [ ] **Step 3: Commit**

```bash
git add benji/ui/widgets/summary_item.py benji/ui/widgets/pending_item.py
git commit -m "feat(ui): SummaryItem + PendingItem widgets"
```

---

## Task 9: Refonte `SummariesTab`

**Files:**
- Modify: `benji/ui/summaries_tab.py`

- [ ] **Step 1: Remplacer intégralement `benji/ui/summaries_tab.py`**

```python
"""Onglet 'Résumés' : liste groupée par jour + preview markdown stylée."""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime, date, timedelta
from pathlib import Path

from PyQt6.QtCore import Qt, QFileSystemWatcher, QSize
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

from benji.ui.style import current_theme, FONT_UI, FONT_MONO, FONT_DISPLAY
from benji.ui.widgets.icons import clipboard_icon, folder_arrow_icon
from benji.ui.widgets.pending_item import PendingItem
from benji.ui.widgets.summary_item import SummaryItem

log = logging.getLogger(__name__)

_SUMMARY_FILENAME = re.compile(r"summary_(\d{8})_(\d{6})\.md$")
_HEADER_PREFIX = "__header__:"
_PENDING_PREFIX = "__pending__:"


def _default_dir() -> Path:
    return Path.home() / ".cache" / "benji" / "summaries"


class SummariesTab(QWidget):
    def __init__(self, summaries_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._dir = summaries_dir or _default_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._pending_text: str = ""
        self._pending_items: dict[str, QListWidgetItem] = {}
        self._build_ui()
        self._wire()
        self.reload()
        self._install_watcher()
        self.apply_theme()

    def _build_ui(self) -> None:
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QListWidget.Shape.NoFrame)
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.setSpacing(2)

        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.setFrameShape(QTextBrowser.Shape.NoFrame)
        self.preview.setPlaceholderText("Cliquez sur un résumé pour le voir")

        self.copy_btn = QPushButton("Copier")
        self.reveal_btn = QPushButton("Révéler dans Finder")
        self.copy_btn.setObjectName("toolbar_btn")
        self.reveal_btn.setObjectName("toolbar_btn")
        self.copy_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)

        right_top = QHBoxLayout()
        right_top.setContentsMargins(12, 8, 12, 4)
        right_top.addWidget(self.copy_btn)
        right_top.addWidget(self.reveal_btn)
        right_top.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(right_top)
        right_layout.addWidget(self.preview, 1)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(self.list_widget)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 7)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 8)
        layout.addWidget(self.splitter)

    def _wire(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_selection)
        self.copy_btn.clicked.connect(self._copy_selected)
        self.reveal_btn.clicked.connect(self._reveal_selected)

    def _install_watcher(self) -> None:
        self._watcher = QFileSystemWatcher([str(self._dir)], self)
        self._watcher.directoryChanged.connect(lambda _: self.reload())

    def apply_theme(self) -> None:
        t = current_theme()
        sel_bg = t.accent_alpha(18)
        hover_bg = t.label_alpha(5)
        separator = t.separator
        self.setStyleSheet(f"""
            SummariesTab, QSplitter, QTextBrowser, QListWidget {{ background: transparent; }}
            QSplitter::handle {{ background-color: rgba({separator.red()},{separator.green()},{separator.blue()},{separator.alpha()}); }}
            QListWidget {{ border: none; outline: none; padding: 8px 6px; }}
            QListWidget::item {{
                border-radius: 6px;
                padding: 0px;
                margin: 1px 4px;
            }}
            QListWidget::item:selected {{
                background-color: rgba({sel_bg.red()},{sel_bg.green()},{sel_bg.blue()},{sel_bg.alpha()});
            }}
            QListWidget::item:hover:!selected {{
                background-color: rgba({hover_bg.red()},{hover_bg.green()},{hover_bg.blue()},{hover_bg.alpha()});
            }}
            QPushButton#toolbar_btn {{
                font-family: {FONT_UI};
                font-size: 12px;
                color: rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()});
                background: transparent;
                border: none;
                padding: 5px 10px;
                border-radius: 5px;
            }}
            QPushButton#toolbar_btn:hover {{
                background-color: rgba({hover_bg.red()},{hover_bg.green()},{hover_bg.blue()},{hover_bg.alpha()});
            }}
            QPushButton#toolbar_btn:disabled {{
                color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()});
            }}
        """)
        label_hex = f"#{t.label.red():02x}{t.label.green():02x}{t.label.blue():02x}"
        self.copy_btn.setIcon(clipboard_icon(label_hex))
        self.reveal_btn.setIcon(folder_arrow_icon(label_hex))
        self._apply_preview_css()
        self._refresh_item_widget_themes()

    def _apply_preview_css(self) -> None:
        t = current_theme()
        label_rgba = f"rgba({t.label.red()},{t.label.green()},{t.label.blue()},{t.label.alpha()})"
        sec_rgba = f"rgba({t.secondary_label.red()},{t.secondary_label.green()},{t.secondary_label.blue()},{t.secondary_label.alpha()})"
        code_bg = t.label_alpha(8)
        code_rgba = f"rgba({code_bg.red()},{code_bg.green()},{code_bg.blue()},{code_bg.alpha()})"
        accent_rgba = f"rgb({t.accent.red()},{t.accent.green()},{t.accent.blue()})"
        css = f"""
            body {{ font-family: {FONT_UI}; font-size: 14px; line-height: 1.6; color: {label_rgba}; padding: 24px 28px; }}
            h1 {{ font-family: {FONT_DISPLAY}; font-size: 22px; font-weight: 600; margin: 0 0 16px 0; }}
            h2 {{ font-size: 17px; font-weight: 600; margin: 20px 0 10px 0; }}
            h3 {{ font-size: 15px; font-weight: 600; margin: 16px 0 8px 0; }}
            p {{ margin: 0 0 12px 0; }}
            code {{ font-family: {FONT_MONO}; font-size: 13px; background-color: {code_rgba}; padding: 1px 5px; border-radius: 3px; }}
            pre {{ background-color: {code_rgba}; padding: 10px 14px; border-radius: 6px; }}
            pre code {{ background: transparent; padding: 0; }}
            blockquote {{ border-left: 3px solid {accent_rgba}; padding-left: 12px; color: {sec_rgba}; margin: 12px 0; }}
            ul, ol {{ margin: 0 0 12px 18px; padding: 0; }}
            li {{ margin-bottom: 4px; }}
            a {{ color: {accent_rgba}; text-decoration: none; }}
        """
        self.preview.document().setDefaultStyleSheet(css)
        # Re-render le markdown courant pour appliquer le CSS
        path = self._selected_path()
        if path and not path.startswith(_PENDING_PREFIX) and not path.startswith(_HEADER_PREFIX):
            try:
                self.preview.setMarkdown(Path(path).read_text(encoding="utf-8"))
            except Exception:
                pass

    def _refresh_item_widget_themes(self) -> None:
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if w is not None and hasattr(w, "apply_theme"):
                w.apply_theme()

    def reload(self) -> None:
        prev_path = self._selected_path()
        files = sorted(
            self._dir.glob("summary_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        self.list_widget.clear()

        # Group by day (today, yesterday, weekday, full date)
        current_group: str | None = None
        for p in files:
            dt = self._dt_from_path(p)
            group = self._group_label(dt.date())
            if group != current_group:
                self._add_header(group)
                current_group = group
            self._add_summary_item(p, dt)

        if prev_path:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == prev_path:
                    self.list_widget.setCurrentRow(i)
                    break

    def _add_header(self, label: str) -> None:
        item = QListWidgetItem(label.upper())
        item.setData(Qt.ItemDataRole.UserRole, f"{_HEADER_PREFIX}{label}")
        item.setFlags(Qt.ItemFlag.NoItemFlags)  # non-sélectionnable
        t = current_theme()
        # Petit padding via sizeHint
        item.setSizeHint(QSize(0, 28))
        # On utilise un widget pour avoir une typo correcte
        from PyQt6.QtWidgets import QLabel
        header = QLabel(label.upper())
        header.setStyleSheet(
            f"font-family: {FONT_UI}; font-size: 10px; font-weight: 600; "
            f"letter-spacing: 0.6px; "
            f"color: rgba({t.tertiary_label.red()},{t.tertiary_label.green()},{t.tertiary_label.blue()},{t.tertiary_label.alpha()}); "
            "padding: 12px 14px 4px 14px; background: transparent;"
        )
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, header)

    def _add_summary_item(self, path: Path, dt: datetime) -> None:
        snippet = self._first_line(path)
        widget = SummaryItem(dt, snippet)
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, str(path))
        item.setSizeHint(widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)

    @staticmethod
    def _dt_from_path(p: Path) -> datetime:
        m = _SUMMARY_FILENAME.search(p.name)
        if m:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        return datetime.fromtimestamp(p.stat().st_mtime)

    @staticmethod
    def _group_label(d: date) -> str:
        today = date.today()
        if d == today:
            return "Aujourd'hui"
        if d == today - timedelta(days=1):
            return "Hier"
        if (today - d).days < 7:
            return d.strftime("%A")
        return d.strftime("%d %B %Y")

    @staticmethod
    def _first_line(p: Path) -> str:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    return (line[:70] + "…") if len(line) > 70 else line
        except Exception:
            pass
        return ""

    def _selected_path(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection(self) -> None:
        path = self._selected_path()
        is_real_file = (
            path is not None
            and not path.startswith(_PENDING_PREFIX)
            and not path.startswith(_HEADER_PREFIX)
        )
        self.copy_btn.setEnabled(is_real_file)
        self.reveal_btn.setEnabled(is_real_file)
        if not is_real_file:
            if path is None:
                self.preview.clear()
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            self.preview.setMarkdown(text)
        except Exception as e:
            self.preview.setPlainText(f"Erreur de lecture : {e}")

    def _copy_selected(self) -> None:
        path = self._selected_path()
        if not path or path.startswith(_PENDING_PREFIX) or path.startswith(_HEADER_PREFIX):
            return
        try:
            QGuiApplication.clipboard().setText(Path(path).read_text(encoding="utf-8"))
        except Exception:
            log.exception("Copy failed")

    def _reveal_selected(self) -> None:
        path = self._selected_path()
        if not path or path.startswith(_PENDING_PREFIX) or path.startswith(_HEADER_PREFIX):
            return
        try:
            subprocess.run(["open", "-R", path], check=False)
        except Exception:
            log.exception("Reveal failed")

    # --- API pour le SummaryWorker ---

    def begin_pending(self, summary_id: str) -> None:
        widget = PendingItem()
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, f"{_PENDING_PREFIX}{summary_id}")
        item.setSizeHint(widget.sizeHint())
        # Insère après l'éventuel premier header
        insert_at = 1 if (self.list_widget.count() > 0 and
                          (self.list_widget.item(0).data(Qt.ItemDataRole.UserRole) or "").startswith(_HEADER_PREFIX)) else 0
        self.list_widget.insertItem(insert_at, item)
        self.list_widget.setItemWidget(item, widget)
        self._pending_items[summary_id] = item
        self.list_widget.setCurrentRow(insert_at)
        self.preview.clear()
        self._pending_text = ""

    def append_chunk(self, summary_id: str, chunk: str) -> None:
        if summary_id not in self._pending_items:
            return
        self._pending_text += chunk
        self.preview.setMarkdown(self._pending_text)

    def finalize_pending(self, summary_id: str, path) -> None:
        item = self._pending_items.pop(summary_id, None)
        if item is not None:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        self.reload()
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == str(path):
                self.list_widget.setCurrentRow(i)
                break

    def fail_pending(self, summary_id: str, error: str) -> None:
        item = self._pending_items.get(summary_id)
        if item is None:
            return
        widget = self.list_widget.itemWidget(item)
        if isinstance(widget, PendingItem):
            widget.set_failed(error)
        item.setData(Qt.ItemDataRole.UserRole, None)
        self._pending_items.pop(summary_id, None)
```

- [ ] **Step 2: Smoke launch**

Run: `uv run benji`
Expected : onglet "Résumés" — liste à gauche avec headers de section ("Aujourd'hui", etc.), items 2 lignes (date semibold + heure mono + snippet gris). Sélection avec fond accent translucide arrondi, hover discret. Preview à droite avec markdown formaté (h1 grand, code blocks avec fond). Boutons "Copier"/"Révéler" en style toolbar (pas de fond bombé).

- [ ] **Step 3: Commit**

```bash
git add benji/ui/summaries_tab.py
git commit -m "feat(ui): SummariesTab — items custom, groupage par jour, preview stylée"
```

---

## Task 10: Smoke test automatisé d'import + instanciation

**Files:**
- Create: `tests/ui/test_main_window_smoke.py`

- [ ] **Step 1: Vérifier que le dossier `tests/ui/` existe (sinon le créer)**

Run: `mkdir -p /Users/guillaumedemerges/Dev/Benji/tests/ui && touch /Users/guillaumedemerges/Dev/Benji/tests/ui/__init__.py`

- [ ] **Step 2: Créer le test**

```python
"""Smoke test : la MainWindow s'instancie sans erreur."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtWidgets import QApplication


class FakeBus(QObject):
    event = pyqtSignal(object)


class FakeWorker(QObject):
    started = pyqtSignal(str)
    chunk = pyqtSignal(str, str)
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)
    def request(self, **kwargs): pass


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_main_window_instantiates(qapp, tmp_path):
    from benji.ui.main_window import MainWindow

    history = MagicMock()
    history.get_since.return_value = []
    bus = FakeBus()
    worker = FakeWorker()

    w = MainWindow(
        bus=bus,
        history=history,
        session_start=datetime.now(),
        summary_worker=worker,
        on_minimize=lambda: None,
    )
    assert w.windowTitle() == "Benji"
    assert w.segmented.currentIndex() in (0, 1)
    w.close()


def test_status_pill_switches(qapp):
    from datetime import datetime
    from benji.ui.widgets.status_pill import StatusPill

    pill = StatusPill(datetime.now())
    pill.set_speaking(True)
    assert pill.status_label.text() == "En écoute"
    pill.set_speaking(False)
    assert pill.status_label.text() == "En attente"
```

- [ ] **Step 3: Lancer le test**

Run: `uv run pytest tests/ui/test_main_window_smoke.py -v`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add tests/ui/__init__.py tests/ui/test_main_window_smoke.py
git commit -m "test(ui): smoke test instanciation MainWindow + StatusPill"
```

---

## Task 11: Mettre à jour les docs

**Files:**
- Modify: `benji/ui/CLAUDE.md`

- [ ] **Step 1: Ajouter les nouveaux fichiers à la liste**

Remplacer le contenu de `benji/ui/CLAUDE.md` par :

```markdown
# benji/ui/

- `overlay.py` — fenêtre sous-titres always-on-top, click-through sur macOS via `NSWindow` level. Poll `display_queue` via `QTimer` — ne doit jamais bloquer la boucle Qt.
- `main_window.py` — fenêtre principale (toolbar + 2 onglets Live/Résumés), style macOS natif (vibrancy + palette adaptive).
- `live_tab.py` — onglet Live : `QScrollArea` avec `ChatItem` widgets + `PartialBubble` flottant.
- `summaries_tab.py` — onglet Résumés : liste groupée par jour + preview markdown stylée.
- `tray.py` — icône menu bar macOS (Quit / History / Live Summary)
- `history_window.py` — log scrollable + stats de session (héritage, non touché par le polish 2026-05-27)
- `live_summary_window.py` — résumé LLM glissant (héritage, non touché)
- `style.py` — palette adaptive light/dark, helpers QSS, vibrancy macOS (NSVisualEffectView).
- `widgets/` — widgets custom : `StatusPill`, `SegmentedControl`, `ChatItem`, `PartialBubble`, `SummaryItem`, `PendingItem`, `icons` (SVG → QIcon).

Raccourcis clavier (attachés à l'overlay) : Ctrl+Shift+H (history), Ctrl+Shift+S (summary), Ctrl+Shift+D (debug macOS).

Le style se recharge automatiquement au changement de thème système (signal `QGuiApplication.styleHints().colorSchemeChanged`).
```

- [ ] **Step 2: Commit**

```bash
git add benji/ui/CLAUDE.md
git commit -m "docs(ui): documenter style.py + widgets/"
```

---

## Self-Review (déjà fait par l'auteur du plan)

- **Couverture spec** : §1 palette → Task 1 ; §2 vibrancy → Task 1+5 ; §3 status pill → Task 3+5 ; §3 boutons → Task 5 ; §4 segmented → Task 4+5 ; §5 LiveTab → Task 6+7 ; §6 SummariesTab → Task 8+9 ; §7 style.py → Task 1 ; §8 compat non-mac → géré par les fallbacks dans `style.py` et le `setStyleSheet` conditionné dans `_apply_theme` ; §10 critères → smoke launch à la fin des tasks 5, 7, 9 et test auto Task 10.
- **Placeholders** : aucun.
- **Type consistency** : `SegmentedControl.setBadge(idx, has_badge)` utilisé à Task 5 et défini à Task 4 ✓. `LiveTab.apply_theme` / `SummariesTab.apply_theme` appelés depuis `MainWindow._apply_theme` et définis dans Task 7 / Task 9 ✓. `StatusPill.set_speaking(bool)` utilisé Task 5 défini Task 3 ✓.

Plan complet.
