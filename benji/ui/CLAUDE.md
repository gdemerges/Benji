# benji/ui/

- `overlay.py` — fenêtre sous-titres always-on-top, click-through sur macOS via `NSWindow` level. Poll `display_queue` via `QTimer` — ne doit jamais bloquer la boucle Qt.
- `tray.py` — icône menu bar macOS (Quit / History / Live Summary)
- `history_window.py` — log scrollable + stats de session
- `live_summary_window.py` — résumé LLM glissant, se met à jour toutes les `STTConfig.live_summary_interval_s` secondes

Raccourcis clavier (attachés à l'overlay) : Ctrl+Shift+H (history), Ctrl+Shift+S (summary), Ctrl+Shift+D (debug macOS).
