# Fenêtre principale Benji — Design

**Date** : 2026-05-27
**Statut** : Spec validée, en attente du plan d'implémentation

## Objectif

Ajouter une fenêtre principale (`MainWindow`) à Benji qui regroupe :

- la transcription temps réel (chat-log scrollable),
- un bouton « Résumer maintenant » qui produit un résumé de la session courante,
- l'historique des résumés sauvegardés avec preview rendu en markdown.

La fenêtre coexiste avec les UI existantes (`SubtitleOverlay`, `HistoryWindow`, `LiveSummaryWindow`) sans les remplacer.

## Modes de lancement

Deux entrées :

- **CLI** (`uv run benji`) — démarre en **overlay seul**, jamais de `MainWindow`. Comportement actuel inchangé pour le workflow dev.
- **App** (`Benji.app` packagée) — démarre en **fenêtre principale**, peut basculer vers l'overlay.

La détection se fait dans `main.py` :

```python
def _launch_mode() -> str:
    if os.environ.get("BENJI_LAUNCH_MODE") == "window":
        return "window"
    if ".app/Contents/MacOS/" in sys.executable:
        return "window"
    return "overlay"
```

Le launcher du `.app` (à fournir lors du packaging, hors scope ce spec) pose `BENJI_LAUNCH_MODE=window`.

## Bascule fenêtre ↔ overlay

État **mutuellement exclusif** géré par un `WindowController` (nouveau, dans `main.py`).

- Disponible **uniquement en mode `.app`** (en CLI, le contrôleur n'existe pas, overlay toujours visible).
- Triggers :
  - Bouton **« Réduire »** dans la toolbar de `MainWindow` → `show_overlay()`.
  - **Click sur l'overlay** sous-titres → `show_window()` (le click handler de `SubtitleOverlay` est installé conditionnellement en mode `.app`).
- État interne : `mode: Literal["window", "overlay"]`, transitions via `show_window()` / `show_overlay()` / `toggle()`.

## Layout de `MainWindow`

`QMainWindow` avec `QTabWidget` (`documentMode=True`) et toolbar unifiée macOS (`setUnifiedTitleAndToolBarOnMac(True)`).

### Toolbar

- **Gauche** : indicateur VAD (point coloré, rouge clignotant quand `speaking=True`, gris sinon) + label de session (`Session · 14:32`).
- **Droite** : bouton **« 📝 Résumer maintenant »** + bouton **« ↘ Réduire »**.

Le bouton Résumer est désactivé tant que :
- aucun final n'a été ajouté à la session courante (`TranscriptionHistory.get_since(session_start)` vide), OU
- un `SummaryWorker` est déjà en cours (un seul résumé concurrent — MLX-LM partage le GPU avec Whisper).

### Onglet 1 — Live (`LiveTab`)

Widget composite :

- **Chat-log** (`QTextEdit` read-only, append HTML formaté) qui empile les finals avec :
  - Timestamp `HH:MM` aligné à gauche
  - Label speaker préfixé si diarization activée (`A:`, `B:`)
  - Texte postprocessé du final
- **Partiel courant** : `QLabel` en italique gris sous le chat-log, mis à jour à chaque event `word` / `final_text` du `DisplayBus`.
- **Auto-scroll** vers le bas activé par défaut ; désactivé temporairement si l'utilisateur scroll up manuellement (sticky-bottom standard : on réactive dès qu'il revient en bas).

### Onglet 2 — Résumés (`SummariesTab`)

`QSplitter` horizontal :

- **Liste** (~30 %, `QListWidget`) : tous les `.md` de `~/.cache/benji/summaries/`, triés desc par mtime. Format item : ligne 1 = `15 nov · 14:32`, ligne 2 = première ligne du contenu tronquée à ~60 caractères, gris.
- **Preview** (~70 %, `QTextBrowser`) : rendu markdown via `setMarkdown()`. Au-dessus, barre fine avec deux boutons : **Copier** (presse-papier) et **Révéler dans Finder** (`subprocess.run(["open", "-R", path])`).
- Placeholder si rien sélectionné : *« Cliquez sur un résumé pour le voir »*.

**Badging sur le titre de l'onglet** :
- `Résumés` quand aucun nouveau résumé
- `Résumés (1●)` quand un résumé est en cours OU est terminé mais pas encore consulté. Le badge s'efface dès que l'utilisateur clique sur l'item.

## Flux de génération d'un résumé

Bouton « Résumer maintenant » cliqué :

1. Insère un item placeholder en haut de la liste : `🟠 En cours… 14:35`. Auto-sélection → la preview se prépare à recevoir les chunks.
2. Récupération du texte source : `"\n".join(e["text"] for e in history.get_since(session_start))` (concaténation des finals de la session courante). Puis `SummaryWorker.request(text=..., summary_id=uuid)` — push dans une queue interne du worker.
3. `SummaryWorker` (un `QThread` qui boucle sur sa queue) appelle `summarize(text, on_token=lambda c: self.chunk.emit(uuid, c))`.
4. À chaque chunk, `SummariesTab` append au `QTextBrowser` de preview (avec `setMarkdown` régulier ou append textuel — détail d'impl à trancher).
5. À la fin :
   - `save_summary(text)` → renvoie `Path` vers le `.md` créé.
   - Item de la liste passe de `🟠 En cours…` à `15 nov · 14:35` (timestamp final).
   - Badge `●` sur l'onglet Résumés (effacé au click).
6. Si exception : item passe à `🔴 Échec — voir logs`, log warning, `failed(uuid, error)` émis, bouton Résumer réactivé.

**Concurrence** : une seule requête à la fois. Si le bouton est cliqué pendant un résumé en cours (ne devrait pas arriver — disabled), la requête est ignorée et un warning est loggé.

## Flux de données & threading

### `DisplayBus` (nouveau)

Aujourd'hui `display_queue` est consommée directement par `SubtitleOverlay._read_queue()` via un `QTimer`. Pour supporter plusieurs consommateurs (overlay + `LiveTab`), on extrait cette logique :

```
Transcriber/VAD --put--> display_queue --[DisplayBus QTimer poll]--> pyqtSignal event(dict)
                                                                      ├──> SubtitleOverlay.on_event
                                                                      └──> LiveTab.on_event   (mode .app seulement)
```

- `DisplayBus` vit dans `benji/ui/display_bus.py`.
- Un seul `QTimer` (16 ms, comme aujourd'hui dans l'overlay) draine la queue et émet le signal `event = pyqtSignal(dict)`.
- N'importe quel widget peut `bus.event.connect(self.on_event)`.
- En mode CLI, seul l'overlay est abonné — comportement identique à aujourd'hui.

### `SummaryWorker` (nouveau)

`QThread` avec :

- Méthode `request(text: str, summary_id: str)` — thread-safe push dans `queue.Queue` interne.
- Boucle `run()` : pour chaque request, exécute `summarize() → save_summary()` et émet les signaux.
- Signals : `started(str)`, `chunk(str, str)`, `finished(str, Path)`, `failed(str, str)`.

Vit dans `benji/llm/summary_worker.py`.

### `WindowController` (nouveau)

Petit objet dans `main.py` (ou `benji/ui/window_controller.py` si le code dépasse 50 lignes). API minimale :

```python
class WindowController:
    def __init__(self, main_window, overlay): ...
    @property
    def mode(self) -> Literal["window", "overlay"]: ...
    def show_window(self): ...    # main_window.show() + overlay.hide()
    def show_overlay(self): ...   # overlay.show() + main_window.hide()
    def toggle(self): ...
```

## Modifications des modules existants

- **`SubtitleOverlay`** : ajout optionnel d'un click handler `on_click: Callable` passé au constructeur, déclenché par `mousePressEvent`. Branché par `main.py` en mode `.app` vers `controller.show_window()`. La logique de `_read_queue()` est extraite vers `DisplayBus` ; l'overlay reçoit ses events via le signal du bus.
- **`tray.py`** : nouvel item « Afficher fenêtre » (visible seulement en mode `.app`) → `controller.show_window()`.
- **`main.py`** : construction conditionnelle de `MainWindow` selon `_launch_mode()`, instanciation de `DisplayBus`, `SummaryWorker`, `WindowController`. Le `live_summarizer` (rolling) reste indépendant et continue d'alimenter `LiveSummaryWindow` (séparée).
- **`HistoryWindow`, `LiveSummaryWindow`** : inchangés, raccourcis `Ctrl+Shift+H` / `Ctrl+Shift+S` conservés.

## Persistance & state

- **Géométrie fenêtre** (`x, y, w, h`) sauvegardée via `QSettings` (`~/Library/Preferences/com.benji.app.plist` sur macOS) ; restaurée au prochain lancement `.app`. Fallback si absent/corrompu : centrée 900×600.
- **Onglet sélectionné** : restauré entre lancements, Live par défaut au premier lancement.
- **Résumé sélectionné dans la preview** : non persisté.
- **Fichiers résumés** : continuent dans `~/.cache/benji/summaries/*.md` (inchangé). La liste est :
  - chargée à l'ouverture de l'onglet Résumés,
  - rafraîchie par un `QFileSystemWatcher` sur ce dossier (capte les ajouts depuis un autre process ou depuis le `SummaryWorker` lui-même).
- **Live log** : non persisté entre sessions ; la `LiveTab` démarre vide à chaque lancement. L'historique cross-session reste dans `HistoryWindow`.

## Gestion d'erreurs

- `SummaryWorker` failure → item rouge dans la liste + log warning, bouton Résumer réactivé, pas de crash.
- Résumé demandé alors qu'aucun final accumulé → bouton désactivé en amont, donc cas non atteint.
- `.md` corrompu / illisible dans la preview → afficher message d'erreur dans le `QTextBrowser`, pas de crash.
- `QSettings` corrompu → fallback géométrie par défaut.
- `DisplayBus` : si un slot lève, on log et on continue (un consumer cassé ne doit pas bloquer les autres).

## Tests

`pytest-qt` (à ajouter aux deps si pas déjà présent) :

- `tests/test_display_bus.py` : un event poussé dans la queue arrive sur tous les abonnés du signal ; un slot qui lève n'interrompt pas les autres.
- `tests/test_summary_worker.py` : mock de `summarize()`, vérifier la séquence `started → chunk×N → finished` et la sauvegarde `.md`.
- `tests/test_window_controller.py` : `toggle()` bascule l'état mutuellement exclusif ; `show_window()` cache l'overlay ; `show_overlay()` cache la fenêtre.
- `tests/test_launch_mode.py` : `_launch_mode()` détecte CLI vs `.app` (mock `sys.executable` et env vars).
- `tests/test_summaries_tab.py` : créer 3 `.md` dans un dossier temp, vérifier que la liste les charge triés desc, que le `QFileSystemWatcher` capte un ajout.

Pas de test E2E sur le rendu Qt — fragile et coûteux. On s'arrête au niveau widget/signal.

## Hors scope (chantiers séparés)

- **Packaging `.app`** via `briefcase` ou `py2app` : signing, notarisation, icône, `Info.plist`, launcher qui pose `BENJI_LAUNCH_MODE=window`. Sera traité dans un spec dédié une fois la `MainWindow` fonctionnelle.
- **Persistance cross-session du live log** : si besoin émerge, ajouter dans un v2.
- **Recherche dans le chat-log ou dans les résumés** : YAGNI pour v1.
- **Migration éventuelle vers Swift natif** : évaluée et écartée — voir notes de discussion (gains perf < 10 %, RAM ÷ 4 mais non bloquante, coût réécriture 4-8 semaines).

## Arborescence cible

```
benji/
  main.py                       # modifié : detection mode, WindowController, DisplayBus wiring
  ui/
    main_window.py              # NOUVEAU
    display_bus.py              # NOUVEAU
    live_tab.py                 # NOUVEAU (peut être inline dans main_window.py si court)
    summaries_tab.py            # NOUVEAU
    overlay.py                  # modifié : click handler optionnel, lecture queue déléguée à DisplayBus
    tray.py                     # modifié : item "Afficher fenêtre" en mode .app
    history_window.py           # inchangé
    live_summary_window.py      # inchangé
    splash.py                   # inchangé
  llm/
    summary_worker.py           # NOUVEAU
    summarizer.py               # inchangé
    live_summary.py             # inchangé
```
