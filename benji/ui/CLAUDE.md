# benji/ui/

- `overlay.py` — fenêtre sous-titres always-on-top, click-through sur macOS via `NSWindow` level. Poll `display_queue` via `QTimer` — ne doit jamais bloquer la boucle Qt.
- `main_window.py` — fenêtre principale (toolbar + 2 onglets Live/Résumés), style macOS natif (vibrancy + palette adaptive).
- `live_tab.py` — onglet Live : `QScrollArea` avec `ChatItem` widgets + `PartialBubble` flottant.
- `summaries_tab.py` — onglet Résumés : liste groupée par jour + preview markdown stylée.
- `tray.py` — icône menu bar macOS (Quit / History / Live Summary ; + section compte pilotée par `benji.account.Session` : Se connecter… / Passer Pro… / Gérer l'abonnement… / Se déconnecter, reconstruite à chaque ouverture via `aboutToShow`)
- `login_dialog.py` — dialogue modal de connexion/inscription (email + mot de passe) câblé à `Session`
- `history_window.py` — log scrollable + stats de session (héritage, non touché par le polish 2026-05-27)
- `live_summary_window.py` — résumé LLM glissant (héritage, non touché)
- `style.py` — palette adaptive light/dark, helpers QSS, vibrancy macOS (`NSVisualEffectView`). Source de vérité pour les couleurs / fonts.
- `widgets/` — widgets custom : `StatusPill`, `SegmentedControl`, `ChatItem`, `PartialBubble`, `SummaryItem`, `PendingItem`, `icons` (SVG → QIcon).

Raccourcis clavier (attachés à l'overlay) : Ctrl+Shift+H (history), Ctrl+Shift+S (summary), Ctrl+Shift+D (debug macOS).

Le style se recharge automatiquement au changement de thème système (signal `QGuiApplication.styleHints().colorSchemeChanged`). Chaque widget custom expose une méthode `apply_theme()` que `MainWindow._apply_theme` propage.
