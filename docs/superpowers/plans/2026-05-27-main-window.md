# Fenêtre principale Benji — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une `MainWindow` PyQt6 (onglets Live + Résumés) coexistant avec l'overlay actuel, avec bascule fenêtre↔overlay en mode `.app` et démarrage overlay-seul en mode CLI.

**Architecture:** Spec : `docs/superpowers/specs/2026-05-27-main-window-design.md`. Composants nouveaux : `DisplayBus` (hub d'events Qt multi-consumer), `WindowController` (bascule mutuellement exclusive), `SummaryWorker` (QThread async), `MainWindow` + `LiveTab` + `SummariesTab`. Refacto minimal de `SubtitleOverlay` pour qu'il consomme le bus au lieu de la queue directement.

**Tech Stack:** Python 3.12, PyQt6, pytest, pytest-qt (nouvelle dep), uv.

---

## Conventions communes

- **Run tests** : `uv run pytest tests/<file> -v` (ajouter `-x` pour stopper au premier échec).
- **Lancer l'app** : `uv run benji` (mode overlay). Tester le mode fenêtre : `BENJI_LAUNCH_MODE=window uv run benji`.
- **Commit** : un commit par tâche, message conventional (`feat:`, `refactor:`, `test:`, `chore:`).
- **TDD strict** : test rouge → code minimal → test vert → commit. Pas de code en avance.

---

## Task 1 : Ajouter pytest-qt aux dépendances

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1 : Ajouter pytest-qt en dep dev**

Repérer la section des deps dev dans `pyproject.toml` (chercher `pytest`). Ajouter `pytest-qt>=4.4` à côté.

Si la section est `[dependency-groups] dev = [...]` (format uv moderne) :
```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.4",
]
```

- [ ] **Step 2 : Synchroniser**

```bash
uv sync
```
Expected: `pytest-qt` installé.

- [ ] **Step 3 : Vérifier que la suite existante passe encore**

```bash
uv run pytest -q
```
Expected: tous les tests passent (19/19 actuellement).

- [ ] **Step 4 : Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pytest-qt for Qt widget tests"
```

---

## Task 2 : Helper `_launch_mode()`

Petit utilitaire pur — TDD facile, sert de fondation pour `main.py`.

**Files:**
- Create: `benji/launch_mode.py`
- Create: `tests/test_launch_mode.py`

- [ ] **Step 1 : Écrire le test rouge**

`tests/test_launch_mode.py` :
```python
import sys

import benji.launch_mode as lm


def test_env_var_window_wins(monkeypatch):
    monkeypatch.setenv("BENJI_LAUNCH_MODE", "window")
    assert lm.launch_mode() == "window"


def test_env_var_overlay_wins(monkeypatch):
    monkeypatch.setenv("BENJI_LAUNCH_MODE", "overlay")
    monkeypatch.setattr(sys, "executable", "/Applications/Benji.app/Contents/MacOS/Benji")
    assert lm.launch_mode() == "overlay"


def test_app_bundle_executable(monkeypatch):
    monkeypatch.delenv("BENJI_LAUNCH_MODE", raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/Benji.app/Contents/MacOS/Benji")
    assert lm.launch_mode() == "window"


def test_cli_default(monkeypatch):
    monkeypatch.delenv("BENJI_LAUNCH_MODE", raising=False)
    monkeypatch.setattr(sys, "executable", "/Users/me/.venv/bin/python")
    assert lm.launch_mode() == "overlay"
```

- [ ] **Step 2 : Run test, expect fail**

```bash
uv run pytest tests/test_launch_mode.py -v
```
Expected: ModuleNotFoundError sur `benji.launch_mode`.

- [ ] **Step 3 : Implémenter**

`benji/launch_mode.py` :
```python
"""Détection du mode de lancement : CLI overlay vs .app fenêtre principale."""

from __future__ import annotations

import os
import sys
from typing import Literal

Mode = Literal["window", "overlay"]


def launch_mode() -> Mode:
    """Renvoie 'window' si lancé comme app .app macOS, 'overlay' sinon.

    Override possible via la variable d'env BENJI_LAUNCH_MODE.
    """
    env = os.environ.get("BENJI_LAUNCH_MODE")
    if env in ("window", "overlay"):
        return env  # type: ignore[return-value]
    if ".app/Contents/MacOS/" in sys.executable:
        return "window"
    return "overlay"
```

- [ ] **Step 4 : Run test, expect pass**

```bash
uv run pytest tests/test_launch_mode.py -v
```
Expected: 4 passed.

- [ ] **Step 5 : Commit**

```bash
git add benji/launch_mode.py tests/test_launch_mode.py
git commit -m "feat: add launch_mode() helper (CLI overlay vs .app window)"
```

---

## Task 3 : `DisplayBus` — hub d'events multi-consumer

Extraction de la logique `_poll_queue` de l'overlay vers un objet partagé.

**Files:**
- Create: `benji/ui/display_bus.py`
- Create: `tests/test_display_bus.py`

- [ ] **Step 1 : Écrire le test rouge**

`tests/test_display_bus.py` :
```python
from queue import Queue

import pytest

from benji.ui.display_bus import DisplayBus


@pytest.fixture
def app(qtbot):
    # qtbot fixture from pytest-qt instantiates a QApplication automatically
    return qtbot


def test_event_dispatched_to_subscribers(app):
    q: Queue = Queue()
    bus = DisplayBus(q, poll_ms=5)
    received_a, received_b = [], []
    bus.event.connect(received_a.append)
    bus.event.connect(received_b.append)
    bus.start()

    q.put({"type": "word", "text": "hello"})
    app.wait(50)

    assert received_a == [{"type": "word", "text": "hello"}]
    assert received_b == [{"type": "word", "text": "hello"}]
    bus.stop()


def test_failing_slot_does_not_block_others(app):
    q: Queue = Queue()
    bus = DisplayBus(q, poll_ms=5)
    received = []
    bus.event.connect(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.event.connect(received.append)
    bus.start()

    q.put({"type": "word", "text": "hi"})
    app.wait(50)

    assert received == [{"type": "word", "text": "hi"}]
    bus.stop()


def test_none_sentinel_ignored(app):
    q: Queue = Queue()
    bus = DisplayBus(q, poll_ms=5)
    received = []
    bus.event.connect(received.append)
    bus.start()

    q.put(None)
    q.put({"type": "word", "text": "x"})
    app.wait(50)

    assert received == [{"type": "word", "text": "x"}]
    bus.stop()
```

- [ ] **Step 2 : Run test, expect fail**

```bash
uv run pytest tests/test_display_bus.py -v
```
Expected: ImportError sur `benji.ui.display_bus`.

- [ ] **Step 3 : Implémenter**

`benji/ui/display_bus.py` :
```python
"""Hub Qt qui draine display_queue et émet un signal multi-consumer.

Permet à plusieurs widgets (overlay + LiveTab) de réagir aux mêmes events
sans dupliquer la lecture de la queue.
"""

from __future__ import annotations

import logging
from queue import Empty, Queue

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger(__name__)


class DisplayBus(QObject):
    event = pyqtSignal(object)  # le signal porte un dict ou un str

    def __init__(self, queue: Queue, poll_ms: int = 16, parent=None):
        super().__init__(parent)
        self._queue = queue
        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._drain)
        self._stopped = False

    def start(self) -> None:
        self._stopped = False
        self._timer.start()

    def stop(self) -> None:
        self._stopped = True
        self._timer.stop()

    def _drain(self) -> None:
        if self._stopped:
            return
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                return
            if item is None:
                continue
            self._emit_safe(item)

    def _emit_safe(self, item) -> None:
        # Qt's default signal dispatch calls each slot in turn. If a slot
        # raises, subsequent slots may be skipped. Wrap our own emission so
        # a buggy consumer doesn't take down the others.
        for receiver in list(self.event.receivers if False else []):  # placeholder
            pass
        try:
            self.event.emit(item)
        except Exception:
            log.exception("DisplayBus subscriber raised")
```

Note : Qt route déjà les signaux à chaque slot indépendamment et capture les exceptions dans `sys.unraisablehook` pour les DirectConnection — la garantie est suffisante en pratique. Le test `test_failing_slot_does_not_block_others` valide ce comportement.

- [ ] **Step 4 : Run test, expect pass**

```bash
uv run pytest tests/test_display_bus.py -v
```
Expected: 3 passed.

Si `test_failing_slot_does_not_block_others` échoue (Qt redéclenche l'exception en mode test) : enrober chaque slot via un wrapper. Ajouter dans `DisplayBus` :

```python
    def subscribe(self, slot) -> None:
        """Subscribe a slot with crash isolation. Préférable à event.connect direct."""
        def _wrapped(item):
            try:
                slot(item)
            except Exception:
                log.exception("DisplayBus subscriber raised")
        self.event.connect(_wrapped)
```

Et adapter le test pour appeler `bus.subscribe(...)` au lieu de `bus.event.connect(...)`. Choisir cette voie si Qt ne fournit pas l'isolation.

- [ ] **Step 5 : Commit**

```bash
git add benji/ui/display_bus.py tests/test_display_bus.py
git commit -m "feat: add DisplayBus for multi-consumer display_queue dispatch"
```

---

## Task 4 : Refactor `SubtitleOverlay` pour consommer le `DisplayBus`

Pas de changement de comportement utilisateur. L'overlay arrête de poller la queue lui-même.

**Files:**
- Modify: `benji/ui/overlay.py` (constructeur + `_poll_queue` + `cleanup`)
- Modify: `benji/main.py` (instancie le bus, le passe à l'overlay)

- [ ] **Step 1 : Modifier le constructeur de SubtitleOverlay**

Dans `benji/ui/overlay.py`, changer la signature `__init__` :

```python
    def __init__(self, bus, config: UIConfig = None, on_click=None):
        """bus: DisplayBus. on_click: callable() appelé sur mousePressEvent (mode .app)."""
```

Remplacer `self.display_queue = display_queue` par `self._bus = bus` et `self._on_click = on_click`.

Supprimer les lignes qui créent et démarrent le `self.poll_timer` à la fin de `__init__`. Remplacer par :

```python
        bus.event.connect(self._dispatch_event)
```

Ajouter méthode `_dispatch_event` (qui reprend la logique de `_poll_queue` item par item) :

```python
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
```

Supprimer la méthode `_poll_queue` (devenue morte).

Dans `cleanup()`, supprimer `self.poll_timer.stop()`.

Ajouter dans la classe (override de `mousePressEvent`) :

```python
    def mousePressEvent(self, event):
        if self._on_click is not None:
            try:
                self._on_click()
            except Exception:
                log.exception("Overlay on_click handler raised")
        super().mousePressEvent(event)
```

- [ ] **Step 2 : Adapter `main.py`**

Dans `benji/main.py`, après création de `display_queue` et avant la construction de l'overlay, créer le bus :

```python
from benji.ui.display_bus import DisplayBus
...
bus = DisplayBus(display_queue)
bus.start()
```

Modifier la création de l'overlay :

```python
overlay = SubtitleOverlay(bus, ui_config)
```

(On laisse `on_click=None` pour l'instant ; sera branché en Task 8.)

Dans la séquence de shutdown (fin de `main()`), ajouter `bus.stop()` avant les joins.

- [ ] **Step 3 : Vérifier que l'app démarre et transcrit comme avant**

```bash
uv run benji
```
Expected : l'overlay s'affiche, parler dans le micro doit produire des sous-titres comme avant. Quitter avec Ctrl+C.

- [ ] **Step 4 : Lancer la suite complète**

```bash
uv run pytest -q
```
Expected: tous les tests passent (anciens + 4 launch_mode + 3 display_bus).

- [ ] **Step 5 : Commit**

```bash
git add benji/ui/overlay.py benji/main.py
git commit -m "refactor: SubtitleOverlay consumes DisplayBus instead of queue directly"
```

---

## Task 5 : `WindowController`

**Files:**
- Create: `benji/ui/window_controller.py`
- Create: `tests/test_window_controller.py`

- [ ] **Step 1 : Écrire le test rouge**

`tests/test_window_controller.py` :
```python
import pytest

from benji.ui.window_controller import WindowController


class FakeWidget:
    def __init__(self):
        self.visible = False
    def show(self):
        self.visible = True
    def hide(self):
        self.visible = False
    def raise_(self):
        pass
    def activateWindow(self):
        pass


def test_initial_mode_window():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="window")
    assert ctl.mode == "window"
    assert win.visible is True
    assert ov.visible is False


def test_initial_mode_overlay():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="overlay")
    assert ctl.mode == "overlay"
    assert win.visible is False
    assert ov.visible is True


def test_show_overlay_hides_window():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="window")
    ctl.show_overlay()
    assert ctl.mode == "overlay"
    assert win.visible is False
    assert ov.visible is True


def test_show_window_hides_overlay():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="overlay")
    ctl.show_window()
    assert ctl.mode == "window"
    assert win.visible is True
    assert ov.visible is False


def test_toggle_alternates():
    win, ov = FakeWidget(), FakeWidget()
    ctl = WindowController(main_window=win, overlay=ov, initial_mode="window")
    ctl.toggle()
    assert ctl.mode == "overlay"
    ctl.toggle()
    assert ctl.mode == "window"
```

- [ ] **Step 2 : Run test, expect fail**

```bash
uv run pytest tests/test_window_controller.py -v
```
Expected: ImportError.

- [ ] **Step 3 : Implémenter**

`benji/ui/window_controller.py` :
```python
"""Bascule mutuellement exclusive entre fenêtre principale et overlay."""

from __future__ import annotations

from typing import Literal

Mode = Literal["window", "overlay"]


class WindowController:
    def __init__(self, main_window, overlay, initial_mode: Mode = "window"):
        self._main = main_window
        self._overlay = overlay
        self._mode: Mode = initial_mode
        if initial_mode == "window":
            self._activate_window()
        else:
            self._activate_overlay()

    @property
    def mode(self) -> Mode:
        return self._mode

    def show_window(self) -> None:
        if self._mode == "window":
            return
        self._activate_window()

    def show_overlay(self) -> None:
        if self._mode == "overlay":
            return
        self._activate_overlay()

    def toggle(self) -> None:
        if self._mode == "window":
            self.show_overlay()
        else:
            self.show_window()

    def _activate_window(self) -> None:
        self._overlay.hide()
        self._main.show()
        self._main.raise_()
        self._main.activateWindow()
        self._mode = "window"

    def _activate_overlay(self) -> None:
        self._main.hide()
        self._overlay.show()
        self._overlay.raise_()
        self._mode = "overlay"
```

- [ ] **Step 4 : Run test, expect pass**

```bash
uv run pytest tests/test_window_controller.py -v
```
Expected: 5 passed.

- [ ] **Step 5 : Commit**

```bash
git add benji/ui/window_controller.py tests/test_window_controller.py
git commit -m "feat: add WindowController for window↔overlay toggle"
```

---

## Task 6 : `SummaryWorker` — résumés async

**Files:**
- Create: `benji/llm/summary_worker.py`
- Create: `tests/test_summary_worker.py`

- [ ] **Step 1 : Écrire le test rouge**

`tests/test_summary_worker.py` :
```python
from pathlib import Path
from unittest.mock import patch

import pytest

from benji.llm.summary_worker import SummaryWorker


@pytest.fixture
def fake_summarize():
    def _summarize(text, language="fr", on_token=None):
        for chunk in ["Voici ", "un ", "résumé."]:
            if on_token:
                on_token(chunk)
        return "Voici un résumé."
    return _summarize


def test_full_lifecycle(qtbot, tmp_path, fake_summarize):
    saved_files: list[Path] = []
    def fake_save(text):
        p = tmp_path / "summary_1.md"
        p.write_text(text)
        saved_files.append(p)
        return p

    started, chunks, finished, failed = [], [], [], []
    worker = SummaryWorker()
    worker.started.connect(lambda sid: started.append(sid))
    worker.chunk.connect(lambda sid, c: chunks.append((sid, c)))
    worker.finished.connect(lambda sid, path: finished.append((sid, path)))
    worker.failed.connect(lambda sid, err: failed.append((sid, err)))

    with patch("benji.llm.summary_worker.summarize", side_effect=fake_summarize), \
         patch("benji.llm.summary_worker.save_summary", side_effect=fake_save):
        worker.start()
        worker.request("Texte source", summary_id="abc")
        qtbot.waitUntil(lambda: len(finished) == 1, timeout=2000)

    assert started == ["abc"]
    assert chunks == [("abc", "Voici "), ("abc", "un "), ("abc", "résumé.")]
    assert finished == [("abc", saved_files[0])]
    assert failed == []
    worker.shutdown()


def test_failure_emits_failed(qtbot, fake_summarize):
    def bad(*a, **kw):
        raise RuntimeError("model crashed")

    failed = []
    worker = SummaryWorker()
    worker.failed.connect(lambda sid, err: failed.append((sid, err)))

    with patch("benji.llm.summary_worker.summarize", side_effect=bad):
        worker.start()
        worker.request("x", summary_id="z")
        qtbot.waitUntil(lambda: len(failed) == 1, timeout=2000)

    assert failed[0][0] == "z"
    assert "model crashed" in failed[0][1]
    worker.shutdown()
```

- [ ] **Step 2 : Run test, expect fail**

```bash
uv run pytest tests/test_summary_worker.py -v
```
Expected: ImportError.

- [ ] **Step 3 : Implémenter**

`benji/llm/summary_worker.py` :
```python
"""QThread async qui exécute summarize() + save_summary() sans bloquer l'UI."""

from __future__ import annotations

import logging
from pathlib import Path
from queue import Queue

from PyQt6.QtCore import QThread, pyqtSignal

from benji.llm.summarizer import save_summary, summarize

log = logging.getLogger(__name__)

_STOP_SENTINEL = object()


class SummaryWorker(QThread):
    started = pyqtSignal(str)               # summary_id
    chunk = pyqtSignal(str, str)            # summary_id, token chunk
    finished = pyqtSignal(str, object)      # summary_id, Path
    failed = pyqtSignal(str, str)           # summary_id, error message

    def __init__(self, language: str = "fr", parent=None):
        super().__init__(parent)
        self._queue: Queue = Queue()
        self._language = language
        self.setObjectName("SummaryWorker")

    def request(self, text: str, summary_id: str) -> None:
        """Thread-safe : enqueue une demande de résumé."""
        self._queue.put((summary_id, text))

    def shutdown(self) -> None:
        self._queue.put(_STOP_SENTINEL)
        self.wait(5000)

    def run(self) -> None:
        log.info("SummaryWorker started")
        while True:
            item = self._queue.get()
            if item is _STOP_SENTINEL:
                break
            sid, text = item
            self.started.emit(sid)
            try:
                full = summarize(
                    text,
                    language=self._language,
                    on_token=lambda c, _sid=sid: self.chunk.emit(_sid, c),
                )
                path = save_summary(full)
                self.finished.emit(sid, path)
            except Exception as e:
                log.exception("Summary failed for %s", sid)
                self.failed.emit(sid, str(e))
        log.info("SummaryWorker stopped")
```

- [ ] **Step 4 : Run test, expect pass**

```bash
uv run pytest tests/test_summary_worker.py -v
```
Expected: 2 passed.

- [ ] **Step 5 : Commit**

```bash
git add benji/llm/summary_worker.py tests/test_summary_worker.py
git commit -m "feat: add SummaryWorker QThread for async summarization"
```

---

## Task 7 : `SummariesTab` widget

**Files:**
- Create: `benji/ui/summaries_tab.py`
- Create: `tests/test_summaries_tab.py`

- [ ] **Step 1 : Écrire le test rouge**

`tests/test_summaries_tab.py` :
```python
from pathlib import Path

import pytest

from benji.ui.summaries_tab import SummariesTab


def _write_summary(dir_path: Path, name: str, content: str) -> Path:
    p = dir_path / name
    p.write_text(content)
    return p


def test_loads_existing_summaries(qtbot, tmp_path):
    _write_summary(tmp_path, "summary_20260527_140000.md", "# Titre A\n\nCorps A")
    _write_summary(tmp_path, "summary_20260527_153000.md", "# Titre B\n\nCorps B")

    tab = SummariesTab(summaries_dir=tmp_path)
    qtbot.addWidget(tab)

    assert tab.list_widget.count() == 2
    # Le plus récent en haut (desc par mtime)
    top_item = tab.list_widget.item(0)
    assert "20260527_153000" in top_item.data(0x0100)  # Qt.ItemDataRole.UserRole = 0x0100


def test_selecting_item_renders_preview(qtbot, tmp_path):
    p = _write_summary(tmp_path, "summary_20260527_140000.md", "# Titre\n\nCorps texte")
    tab = SummariesTab(summaries_dir=tmp_path)
    qtbot.addWidget(tab)

    tab.list_widget.setCurrentRow(0)
    qtbot.wait(50)

    # toMarkdown sur QTextBrowser ne renvoie pas exactement l'input à cause du rendu HTML.
    # On vérifie que la source brute correspond au contenu du fichier.
    assert "Titre" in tab.preview.toPlainText()
    assert "Corps texte" in tab.preview.toPlainText()


def test_filewatcher_picks_up_new_file(qtbot, tmp_path):
    tab = SummariesTab(summaries_dir=tmp_path)
    qtbot.addWidget(tab)
    assert tab.list_widget.count() == 0

    _write_summary(tmp_path, "summary_20260527_140000.md", "# Nouveau\n\nx")
    qtbot.waitUntil(lambda: tab.list_widget.count() == 1, timeout=2000)
```

- [ ] **Step 2 : Run test, expect fail**

```bash
uv run pytest tests/test_summaries_tab.py -v
```
Expected: ImportError.

- [ ] **Step 3 : Implémenter**

`benji/ui/summaries_tab.py` :
```python
"""Onglet 'Résumés' : liste à gauche, preview markdown à droite."""

from __future__ import annotations

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QFileSystemWatcher
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QPushButton,
    QSplitter, QTextBrowser, QVBoxLayout, QWidget,
)

log = logging.getLogger(__name__)

_SUMMARY_FILENAME = re.compile(r"summary_(\d{8})_(\d{6})\.md$")


def _default_dir() -> Path:
    return Path.home() / ".cache" / "benji" / "summaries"


class SummariesTab(QWidget):
    def __init__(self, summaries_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self._dir = summaries_dir or _default_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._build_ui()
        self._wire()
        self.reload()
        self._install_watcher()

    def _build_ui(self) -> None:
        self.list_widget = QListWidget()
        self.preview = QTextBrowser()
        self.preview.setOpenExternalLinks(True)
        self.preview.setPlaceholderText("Cliquez sur un résumé pour le voir")

        self.copy_btn = QPushButton("Copier")
        self.reveal_btn = QPushButton("Révéler dans Finder")
        self.copy_btn.setEnabled(False)
        self.reveal_btn.setEnabled(False)

        right_top = QHBoxLayout()
        right_top.addWidget(self.copy_btn)
        right_top.addWidget(self.reveal_btn)
        right_top.addStretch()

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(right_top)
        right_layout.addWidget(self.preview, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.list_widget)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def _wire(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_selection)
        self.copy_btn.clicked.connect(self._copy_selected)
        self.reveal_btn.clicked.connect(self._reveal_selected)

    def _install_watcher(self) -> None:
        self._watcher = QFileSystemWatcher([str(self._dir)], self)
        self._watcher.directoryChanged.connect(lambda _: self.reload())

    def reload(self) -> None:
        prev_path = self._selected_path()
        files = sorted(
            self._dir.glob("summary_*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        self.list_widget.clear()
        for p in files:
            item = QListWidgetItem(self._format_label(p))
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.list_widget.addItem(item)
        # Restore selection if still present
        if prev_path:
            for i in range(self.list_widget.count()):
                if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == prev_path:
                    self.list_widget.setCurrentRow(i)
                    break

    def _format_label(self, p: Path) -> str:
        m = _SUMMARY_FILENAME.search(p.name)
        if m:
            dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            head = dt.strftime("%d %b · %H:%M")
        else:
            head = p.stem
        snippet = self._first_line(p)
        return f"{head}\n{snippet}" if snippet else head

    @staticmethod
    def _first_line(p: Path) -> str:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    return (line[:60] + "…") if len(line) > 60 else line
        except Exception:
            pass
        return ""

    def _selected_path(self) -> str | None:
        item = self.list_widget.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_selection(self) -> None:
        path = self._selected_path()
        has = path is not None
        self.copy_btn.setEnabled(has)
        self.reveal_btn.setEnabled(has)
        if not has:
            self.preview.clear()
            return
        try:
            text = Path(path).read_text(encoding="utf-8")
            self.preview.setMarkdown(text)
        except Exception as e:
            self.preview.setPlainText(f"Erreur de lecture : {e}")

    def _copy_selected(self) -> None:
        path = self._selected_path()
        if not path:
            return
        try:
            QGuiApplication.clipboard().setText(Path(path).read_text(encoding="utf-8"))
        except Exception:
            log.exception("Copy failed")

    def _reveal_selected(self) -> None:
        path = self._selected_path()
        if not path:
            return
        try:
            subprocess.run(["open", "-R", path], check=False)
        except Exception:
            log.exception("Reveal failed")
```

- [ ] **Step 4 : Run test, expect pass**

```bash
uv run pytest tests/test_summaries_tab.py -v
```
Expected: 3 passed. Le test du watcher peut être lent — laisser le timeout à 2 s.

- [ ] **Step 5 : Commit**

```bash
git add benji/ui/summaries_tab.py tests/test_summaries_tab.py
git commit -m "feat: add SummariesTab (list + markdown preview + filesystem watcher)"
```

---

## Task 8 : `LiveTab` widget

Pas de test unitaire automatisé (widget de pur rendu, dépendant d'events) — on vérifie à la main au lancement.

**Files:**
- Create: `benji/ui/live_tab.py`

- [ ] **Step 1 : Implémenter le widget**

`benji/ui/live_tab.py` :
```python
"""Onglet 'Live' : chat-log scrollable des finals + partiel en italique."""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QLabel, QTextEdit, QVBoxLayout, QWidget


class LiveTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._partial_text: str = ""
        self._user_scrolled_up = False
        self.log.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _build_ui(self) -> None:
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet("QTextEdit { font-size: 14px; }")

        self.partial = QLabel("")
        self.partial.setWordWrap(True)
        self.partial.setStyleSheet("color: gray; font-style: italic; padding: 4px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.log, 1)
        layout.addWidget(self.partial)

    def on_event(self, item) -> None:
        """Slot abonné au DisplayBus. Met à jour le chat-log et le partiel."""
        if not isinstance(item, dict):
            return
        msg_type = item.get("type")
        if msg_type == "segment_start":
            self._partial_text = ""
            self.partial.setText("")
        elif msg_type == "word":
            text = item.get("text", "")
            sep = "" if (self._partial_text.endswith(" ") or text.startswith((".", ",", "!", "?", ";", ":"))) else " "
            self._partial_text = (self._partial_text + sep + text).strip()
            self.partial.setText(self._partial_text)
        elif msg_type == "final_text":
            text = item.get("text", "")
            drop = item.get("drop", False)
            if drop or not text:
                self._partial_text = ""
                self.partial.setText("")
                return
            self._append_final(text)
            self._partial_text = ""
            self.partial.setText("")

    def _append_final(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M")
        html = f'<div style="margin-bottom:6px"><span style="color:#888">{ts}</span>&nbsp;&nbsp;{self._escape(text)}</div>'
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        if not self._user_scrolled_up:
            self._scroll_to_bottom()

    def _escape(self, text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def _scroll_to_bottom(self) -> None:
        sb = self.log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_scroll(self, value: int) -> None:
        sb = self.log.verticalScrollBar()
        # Si on est à moins de 20 px du bas, on considère "collé en bas"
        self._user_scrolled_up = (sb.maximum() - value) > 20
```

- [ ] **Step 2 : Sanity-check syntaxe**

```bash
uv run python -c "from benji.ui.live_tab import LiveTab; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3 : Vérifier que la suite passe encore**

```bash
uv run pytest -q
```
Expected: tous les tests passent.

- [ ] **Step 4 : Commit**

```bash
git add benji/ui/live_tab.py
git commit -m "feat: add LiveTab (chat-log + italic partial)"
```

---

## Task 9 : `MainWindow` (assemblage)

**Files:**
- Create: `benji/ui/main_window.py`

- [ ] **Step 1 : Implémenter la fenêtre**

`benji/ui/main_window.py` :
```python
"""Fenêtre principale : toolbar + onglets Live/Résumés."""

from __future__ import annotations

import logging
import platform
import uuid
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QLabel, QMainWindow, QTabWidget, QToolBar, QWidget,
)

from benji.ui.live_tab import LiveTab
from benji.ui.summaries_tab import SummariesTab

log = logging.getLogger(__name__)

_SETTINGS_ORG = "benji"
_SETTINGS_APP = "benji"
_GEOM_KEY = "main_window/geometry"
_TAB_KEY = "main_window/tab_index"


class MainWindow(QMainWindow):
    def __init__(
        self,
        bus,
        history,                       # TranscriptionHistory
        session_start: datetime,
        summary_worker,                # SummaryWorker
        on_minimize=None,              # callable() → bascule overlay
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

    def _build_ui(self) -> None:
        # Onglets
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.live_tab = LiveTab()
        self.summaries_tab = SummariesTab()
        self.tabs.addTab(self.live_tab, "Live")
        self.tabs.addTab(self.summaries_tab, "Résumés")
        self.setCentralWidget(self.tabs)

        # DisplayBus → LiveTab
        self._bus.event.connect(self.live_tab.on_event)
        # Et VAD pin indicator
        self._bus.event.connect(self._update_vad_indicator)

        # Toolbar
        tb = QToolBar("main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.vad_label = QLabel("● Session démarrée")
        self.vad_label.setStyleSheet("color: gray; padding-left: 8px;")
        tb.addWidget(self.vad_label)

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy().Preferred)
        tb.addWidget(spacer)

        self.summarize_action = QAction("📝 Résumer maintenant", self)
        self.summarize_action.triggered.connect(self._request_summary)
        tb.addAction(self.summarize_action)

        self.minimize_action = QAction("↘ Réduire", self)
        self.minimize_action.triggered.connect(self._minimize)
        tb.addAction(self.minimize_action)

        # Tab badge dirty bit
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Bouton "Résumer" désactivé tant qu'aucun final accumulé
        self._refresh_summarize_enabled()

    def _wire_worker(self) -> None:
        self._worker.started.connect(self._on_summary_started)
        self._worker.chunk.connect(self._on_summary_chunk)
        self._worker.finished.connect(self._on_summary_finished)
        self._worker.failed.connect(self._on_summary_failed)
        # Permet de réactiver le bouton après chaque utterance
        self._bus.event.connect(self._maybe_refresh_summarize_enabled)

    def _update_vad_indicator(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "vad_status":
            if item.get("speaking"):
                self.vad_label.setText("🔴 En écoute")
                self.vad_label.setStyleSheet("color: #e44; padding-left: 8px;")
            else:
                self.vad_label.setText("● En attente")
                self.vad_label.setStyleSheet("color: gray; padding-left: 8px;")

    def _maybe_refresh_summarize_enabled(self, item) -> None:
        if isinstance(item, dict) and item.get("type") == "final_text" and item.get("text"):
            self._refresh_summarize_enabled()

    def _refresh_summarize_enabled(self) -> None:
        has_history = bool(self._history.get_since(self._session_start))
        idle = self._pending_summary_id is None
        self.summarize_action.setEnabled(has_history and idle)

    def _request_summary(self) -> None:
        entries = self._history.get_since(self._session_start)
        if not entries:
            return
        text = "\n".join(e["text"] for e in entries)
        sid = uuid.uuid4().hex
        self._pending_summary_id = sid
        self._refresh_summarize_enabled()
        self.summaries_tab.begin_pending(sid)
        self._worker.request(text=text, summary_id=sid)

    def _on_summary_started(self, sid: str) -> None:
        log.info("Summary started: %s", sid)

    def _on_summary_chunk(self, sid: str, chunk: str) -> None:
        self.summaries_tab.append_chunk(sid, chunk)

    def _on_summary_finished(self, sid: str, path: Path) -> None:
        self.summaries_tab.finalize_pending(sid, path)
        self._pending_summary_id = None
        self._has_unread_summary = (self.tabs.currentIndex() != 1)
        self._refresh_tab_badge()
        self._refresh_summarize_enabled()

    def _on_summary_failed(self, sid: str, err: str) -> None:
        self.summaries_tab.fail_pending(sid, err)
        self._pending_summary_id = None
        self._refresh_summarize_enabled()

    def _on_tab_changed(self, idx: int) -> None:
        if idx == 1:
            self._has_unread_summary = False
            self._refresh_tab_badge()

    def _refresh_tab_badge(self) -> None:
        base = "Résumés"
        if self._pending_summary_id is not None:
            self.tabs.setTabText(1, f"{base} (1●)")
        elif self._has_unread_summary:
            self.tabs.setTabText(1, f"{base} ●")
        else:
            self.tabs.setTabText(1, base)

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
                self.resize(900, 600)
        else:
            self.resize(900, 600)
        tab = s.value(_TAB_KEY, 0, type=int)
        self.tabs.setCurrentIndex(tab)

    def closeEvent(self, event) -> None:
        s = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        s.setValue(_GEOM_KEY, self.saveGeometry())
        s.setValue(_TAB_KEY, self.tabs.currentIndex())
        super().closeEvent(event)
```

- [ ] **Step 2 : Étendre `SummariesTab` avec les méthodes pending**

Dans `benji/ui/summaries_tab.py`, après `_install_watcher`, ajouter :

```python
    # --- API pour le SummaryWorker en cours ---
    def begin_pending(self, summary_id: str) -> None:
        item = QListWidgetItem(f"🟠 En cours…\n{datetime.now().strftime('%H:%M:%S')}")
        item.setData(Qt.ItemDataRole.UserRole, f"__pending__:{summary_id}")
        self.list_widget.insertItem(0, item)
        self.list_widget.setCurrentRow(0)
        self.preview.clear()
        self._pending_text: str = ""

    def append_chunk(self, summary_id: str, chunk: str) -> None:
        item = self._find_pending(summary_id)
        if item is None:
            return
        self._pending_text = getattr(self, "_pending_text", "") + chunk
        self.preview.setMarkdown(self._pending_text)

    def finalize_pending(self, summary_id: str, path) -> None:
        item = self._find_pending(summary_id)
        if item is not None:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        # File watcher catches the new .md, but reload immediately for snappy UX.
        self.reload()
        # Sélectionner le nouveau .md
        for i in range(self.list_widget.count()):
            if self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) == str(path):
                self.list_widget.setCurrentRow(i)
                break

    def fail_pending(self, summary_id: str, error: str) -> None:
        item = self._find_pending(summary_id)
        if item is None:
            return
        item.setText(f"🔴 Échec — {error[:80]}")
        item.setData(Qt.ItemDataRole.UserRole, None)

    def _find_pending(self, summary_id: str):
        marker = f"__pending__:{summary_id}"
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == marker:
                return it
        return None
```

- [ ] **Step 3 : Sanity-check imports**

```bash
uv run python -c "from benji.ui.main_window import MainWindow; print('ok')"
```
Expected: `ok`.

- [ ] **Step 4 : Vérifier que tous les tests passent encore**

```bash
uv run pytest -q
```
Expected: tous verts.

- [ ] **Step 5 : Commit**

```bash
git add benji/ui/main_window.py benji/ui/summaries_tab.py
git commit -m "feat: add MainWindow with Live + Summaries tabs"
```

---

## Task 10 : Wire le tout dans `main.py`

Branche `MainWindow`, `WindowController`, `SummaryWorker`, et l'overlay click handler en mode `.app`. Le mode CLI reste strictement inchangé côté UX.

**Files:**
- Modify: `benji/main.py`

- [ ] **Step 1 : Imports et détection du mode**

Ajouter en haut de `main.py` (avec les autres imports `benji.*`) :

```python
from benji.launch_mode import launch_mode
from benji.ui.window_controller import WindowController
from benji.ui.main_window import MainWindow
from benji.llm.summary_worker import SummaryWorker
```

- [ ] **Step 2 : Brancher selon le mode**

Dans `main()`, après `overlay = SubtitleOverlay(bus, ui_config)` (refactoré en Task 4) et après la création de `history_window` / `live_summary_window` / tray, ajouter :

```python
mode = launch_mode()
log.info("Launch mode: %s", mode)

main_window = None
controller = None
summary_worker = None

if mode == "window":
    summary_worker = SummaryWorker(language=stt_config.language or "fr")
    summary_worker.start()

    main_window = MainWindow(
        bus=bus,
        history=transcriber.history,
        session_start=session_start,
        summary_worker=summary_worker,
        on_minimize=lambda: controller.show_overlay(),
    )

    controller = WindowController(
        main_window=main_window,
        overlay=overlay,
        initial_mode="window",
    )

    # Click sur overlay → revient à la fenêtre
    overlay._on_click = lambda: controller.show_window()
else:
    # CLI : overlay seul, comportement actuel
    overlay.show()
```

(Le test `controller._on_click = ...` est ok mais peu propre — quand cette task est implémentée, exposer `set_on_click(cb)` sur l'overlay si le reviewer le demande. Pour MVP, accès attribut direct.)

- [ ] **Step 3 : Étendre la tray en mode .app**

Dans `tray = build_tray(...)`, on a besoin de passer la `main_window` si elle existe. Modifier la signature :

`benji/ui/tray.py` : ajouter un paramètre `main_window=None`. Si non nul, ajouter avant l'item Quit :

```python
    if main_window is not None:
        show_main = QAction("Afficher fenêtre", parent)
        show_main.triggered.connect(lambda: (main_window.show(), main_window.raise_(), main_window.activateWindow()))
        menu.addAction(show_main)
```

Et dans `main.py` :
```python
tray = build_tray(history_window, live_summary_window, main_window=main_window)
```

- [ ] **Step 4 : Shutdown propre**

À la fin de `main()`, avant les joins, ajouter :

```python
if summary_worker is not None:
    summary_worker.shutdown()
bus.stop()
```

- [ ] **Step 5 : Test manuel — mode CLI**

```bash
uv run benji
```
Expected : comportement strictement identique à avant. Overlay s'affiche, sous-titres apparaissent. Ctrl+C quitte proprement.

- [ ] **Step 6 : Test manuel — mode fenêtre**

```bash
BENJI_LAUNCH_MODE=window uv run benji
```
Expected :
- La `MainWindow` s'ouvre, overlay caché.
- L'onglet Live affiche les utterances finales au fil de la parole, avec timestamps. Le partiel apparaît en italique gris.
- Clic « Réduire » → fenêtre se cache, overlay apparaît, transcription continue sur l'overlay.
- Clic sur l'overlay → fenêtre réapparaît.
- Clic « Résumer maintenant » → badge `(1●)` sur l'onglet Résumés, item « En cours… » dans la liste, preview qui se remplit token par token. Badge devient `●` quand fini. Clic sur l'onglet → badge disparaît.
- Le fichier `.md` apparaît dans `~/.cache/benji/summaries/`.
- Fermer la fenêtre (Cmd+Q ou bouton rouge) puis relancer → la géométrie est restaurée.

- [ ] **Step 7 : Vérifier que la suite complète passe**

```bash
uv run pytest -q
```
Expected: tous verts.

- [ ] **Step 8 : Commit**

```bash
git add benji/main.py benji/ui/tray.py
git commit -m "feat: wire MainWindow + WindowController in .app launch mode"
```

---

## Vérification finale

- [ ] `uv run pytest -q` — tout vert
- [ ] `uv run benji` — comportement CLI inchangé
- [ ] `BENJI_LAUNCH_MODE=window uv run benji` — fenêtre, bascule, résumé, persistance OK
- [ ] Git log propre, un commit par task

## Hors plan (pour mémoire)

- Packaging `.app` via `briefcase` ou `py2app` → spec séparée.
- Migration éventuelle Swift natif → écartée (gains < 10 %, coût 4-8 semaines).
