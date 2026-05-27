# Polish esthétique fenêtre principale — Glass macOS natif

**Date :** 2026-05-27
**Type :** Polish visuel + retouches ergonomiques
**Portée :** `benji/ui/main_window.py`, `live_tab.py`, `summaries_tab.py`, nouveau `style.py`

## Contexte

La fenêtre principale (`MainWindow` + `LiveTab` + `SummariesTab`) est fonctionnelle mais affiche le style Qt par défaut : gris système brut, tabs natifs Qt, QTextEdit sans typographie travaillée, boutons natifs. L'objectif est un polish visuel cohérent dans l'esprit **macOS natif raffiné** (Apple première-partie), sans refonte structurelle.

## Direction esthétique

**Glass macOS natif, palette adaptative light/dark.**

- Embrasse les conventions macOS : translucidité (vibrancy), titlebar unifié, couleur d'accent système, SF Pro.
- Sensation visée : app Apple première-partie (esprit Voice Memos / Notes / Music).
- Adaptive : suit automatiquement le thème système, recalcul instantané au changement.

## 1. Système de design global

### 1.1 Palette

- **Background fenêtre** : translucide via `NSVisualEffectView` material `underWindowBackground` (vibrancy automatique selon thème système).
- **Hiérarchie texte** : couleurs **système macOS** uniquement (récupérées via `QPalette` ou `NSColor` bridgé) :
  - `labelColor` → corps de texte
  - `secondaryLabelColor` → labels secondaires, métadonnées
  - `tertiaryLabelColor` → timestamps, hints
  - `quaternaryLabelColor` → séparateurs, fonds très subtils
- **Accent principal** : `QPalette.Highlight` (mappe sur l'accent macOS utilisateur, bleu par défaut).
- **Accent "live"** : `#FF453A` (rouge système macOS dark) / `#FF3B30` (light) — réservé exclusivement à l'état "en écoute". Source de vérité : `NSColor.systemRedColor`.

### 1.2 Typographie

- Famille principale : **SF Pro Text** (`-apple-system`, fallback `.AppleSystemUIFont`).
- Monospace (timestamps) : **SF Mono**, fallback `Menlo`.
- Échelle :
  - 22px / Semibold → titres d'écran (rares)
  - 15px / Regular → corps de texte Live
  - 13px / Regular → corps secondaire, listes
  - 11px / Medium / Mono → timestamps, métadonnées

### 1.3 Spacing

- Marges fenêtre : 16-20px.
- Espacement vertical entre items chat : 14px.
- Padding interne des cards : 12-16px.
- Border radius standard : 8px (cards), 6px (sélection liste), 10px (status pill).

### 1.4 Détection du thème

- `QApplication.styleHints().colorScheme()` à l'init.
- Connexion au signal `colorSchemeChanged` → rebuild des stylesheets via `apply_theme()`.

## 2. Window chrome

- **Vibrancy** : attacher un `NSVisualEffectView` au content view de la `NSWindow` sous-jacente (récupérée via `self.winId()` + PyObjC).
  - Material : `NSVisualEffectMaterialUnderWindowBackground`.
  - Blending : `NSVisualEffectBlendingModeBehindWindow`.
  - State : `NSVisualEffectStateActive`.
- **Titlebar** : `setUnifiedTitleAndToolBarOnMac(True)` (déjà en place), titre "Benji" discret.
- **Toolbar** : fond transparent (hérite vibrancy), pas de séparateur visible avec la zone tabs.

## 3. Header (toolbar)

### 3.1 Status pill (gauche)

Widget custom `StatusPill(QWidget)` à la place du `QLabel` actuel :

- Layout horizontal : `[●  En écoute · 03:42]`
- **Dot** : QWidget 8×8px, border-radius 4px.
  - Couleur rouge accent quand `vad_status.speaking == True`.
  - Couleur `tertiaryLabelColor` sinon.
  - **Animation pulse** : `QPropertyAnimation` sur `opacity` (1.0 ↔ 0.4), durée 1200ms, easing `InOutSine`, loop infini — active uniquement en écoute.
- **Texte** : "En écoute" / "En attente" + " · " + timer session `mm:ss`.
  - Timer : `QTimer` 1s qui calcule `datetime.now() - session_start`.
  - Au-delà d'1h, format `hh:mm:ss`.
- Fond pill : `quaternaryLabelColor` translucide, padding 4px 10px, border-radius 10px.

### 3.2 Boutons d'action (droite)

- **"Résumer"** : style **filled accent** (fond `QPalette.Highlight`, texte blanc), icône SF-symbol-like "doc.text" + label.
- **"Réduire"** : style **ghost** (texte `labelColor`, fond transparent, hover `quaternaryLabelColor`), icône "arrow.down.right.and.arrow.up.left".
- Icônes : générées en SVG inline (formes basiques flèche / document), wrappées en `QIcon` via `QPixmap`. Fallback emoji si problème.
- Taille bouton : 28px hauteur, padding 8px 12px, border-radius 6px.

## 4. Onglets (segmented control)

Remplacer le `QTabWidget` natif par un **segmented control** custom positionné sous la toolbar :

- Conteneur centré, largeur ~280px, hauteur 28px.
- Deux segments : "Live" / "Résumés".
- Fond global : `quaternaryLabelColor` translucide, border-radius 7px.
- Segment actif : fond `labelColor` 12% opacity, texte `labelColor`, transition 180ms.
- Segment inactif : texte `secondaryLabelColor`.
- **Badge non-lu** sur "Résumés" : petit dot 6px accent à droite du label, pas le texte `(1●)`.
- Implémentation : `QStackedWidget` pour le contenu + widget `SegmentedControl(QWidget)` custom au-dessus (deux `QPushButton` checkable mutually exclusive stylés).

Le contrat avec `MainWindow` reste : `tabs.setCurrentIndex(i)`, `tabs.currentChanged` signal, `tabs.setTabText(...)` (remplacé par `set_badge(index, has_badge)`).

## 5. Onglet Live

### 5.1 Layout

- `LiveTab` reçoit un `QScrollArea` contenant un widget central de **largeur max 720px**, marges horizontales adaptatives (`stretch` de chaque côté).
- Le chat-log devient un `QVBoxLayout` de widgets `ChatItem` (au lieu d'un `QTextEdit` monolithique). Permet animations + stylage fin.

### 5.2 ChatItem

Widget pour chaque message final :

- Layout horizontal : `[timestamp 48px fixed]  [texte 1.0 stretch]`.
- Timestamp : SF Mono 11px, `tertiaryLabelColor`, aligné top.
- Texte : SF Pro 15px, `labelColor`, `wordWrap=True`, line-height 1.5 (via `QTextDocument` ou padding manuel).
- Espacement : margin-bottom 14px.
- Apparition : fade-in 200ms (`QGraphicsOpacityEffect` + `QPropertyAnimation`).

### 5.3 Partiel (carte flottante)

- Widget `PartialBubble(QWidget)` en bas, **toujours visible** (réservé sticky en bas du scroll).
- Fond : accent `QPalette.Highlight` à 8% opacity, border-radius 8px, padding 10px 14px.
- Texte : SF Pro 14px italique, `secondaryLabelColor`.
- **Curseur clignotant** à la fin du texte : barre 2×16px qui blink 600ms (animé via QTimer).
- Vide → bubble masquée (`setVisible(False)`).

### 5.4 Auto-scroll

Comportement identique à l'actuel (détection "user scrolled up" → ne pas auto-scroller), mais via le scrollbar du `QScrollArea`.

## 6. Onglet Résumés

### 6.1 Liste gauche

Remplacer `QListWidget` par un `QListView` + modèle custom (ou garder `QListWidget` avec `setItemWidget` pour items custom). Choix : **`QListWidget` + items custom widgets** (plus simple, suffisant).

- **SummaryItem** widget :
  - Date "26 mai" en SF Pro Semibold 14px `labelColor`.
  - Heure "14:32" en SF Mono 11px `tertiaryLabelColor` (côte à côte avec la date).
  - Snippet : SF Pro 12px `secondaryLabelColor`, 1 ligne max + ellipsis.
  - Padding 10px 14px, border-radius 6px (visible en sélection).
- **Sélection** : fond accent à 15% opacity (pas le bleu Qt brut), border-radius 6px.
- **Hover** : fond `quaternaryLabelColor` 50%.
- **Groupage par jour** : headers de section non-sélectionnables "Aujourd'hui" / "Hier" / "Lundi 26 mai" :
  - SF Pro Semibold 11px uppercase, `tertiaryLabelColor`, padding 16px 14px 6px 14px.
  - Logique de regroupement basée sur `datetime.now().date()` vs date du fichier.

### 6.2 Preview droite

- `QTextBrowser` avec **CSS markdown soigné** injecté dans le setHtml (Qt `setMarkdown` génère un HTML qu'on peut surcharger via `document().setDefaultStyleSheet(...)`) :
  - Padding interne 24px 28px.
  - h1 : SF Pro Display 22px Semibold, margin-bottom 16px.
  - h2 : SF Pro 17px Semibold, margin-top 20px.
  - body : SF Pro 14px, line-height 1.6.
  - code inline : SF Mono 13px, fond `quaternaryLabelColor`, padding 1px 4px, radius 3px.
  - code blocks : fond `quaternaryLabelColor`, padding 10px 14px, radius 6px.
  - blockquote : border-left 3px accent, padding-left 12px, `secondaryLabelColor`.

### 6.3 Boutons "Copier" / "Révéler"

- Style **toolbar button macOS** : pas de fond, hover `quaternaryLabelColor`, padding 6px 12px, radius 5px, texte 12px `labelColor`.
- Icônes SVG inline (clipboard / folder-arrow).

### 6.4 État "en cours"

Remplacer l'item texte "🟠 En cours…" par un **PendingItem** widget custom :

- Texte "Génération du résumé…" en `secondaryLabelColor`.
- **Spinner** : `QProgressBar` mode indeterminate stylé en pill fin (hauteur 3px, fond `quaternaryLabelColor`, chunk accent, radius 1.5px).
- Pas de sélection ronde — fond accent 8% en permanence pendant le pending.

État échec : fond rouge accent 8%, texte "Échec : <error>" en rouge accent.

## 7. Implémentation — `benji/ui/style.py` (nouveau)

Module central :

```
benji/ui/style.py
  class Theme:
      # Cache des couleurs résolues selon dark/light
      label, secondary_label, tertiary_label, quaternary_label
      accent, accent_alpha(pct), live_red, separator
      window_background  # pour fallback non-mac

  def current_theme() -> Theme
  def stylesheet_for(component_name: str) -> str
      # Templates QSS interpolés avec les couleurs du thème courant

  def apply_window_vibrancy(window: QWidget) -> None
      # macOS : NSVisualEffectView, no-op ailleurs

  def install_theme_listener(callback) -> None
      # Wire QApplication.styleHints().colorSchemeChanged
```

Tous les widgets custom (`StatusPill`, `SegmentedControl`, `ChatItem`, `PartialBubble`, `SummaryItem`, `PendingItem`) consomment `current_theme()` et se rebuildent au signal de changement de thème.

## 8. Compatibilité non-macOS

- Vibrancy : no-op, fallback fond opaque `window_background`.
- SF Pro / SF Mono : fallback `system-ui` / `monospace` via QSS font-family chain.
- Reste du design : strictement identique (couleurs, espacements, animations).

## 9. Out of scope

- L'overlay sous-titres (`overlay.py`), la `history_window.py`, la `live_summary_window.py`, la `splash.py`, le tray — pas touchés dans cette itération.
- Pas de nouveaux contrôles fonctionnels (pas de pause/reprise, pas de paramètres exposés).
- Pas de structure changée (toujours toolbar + 2 onglets).

## 10. Critères de succès

- Visuellement, la fenêtre passe le test "on dirait une app Apple" — pas de gris Qt brut, pas de boutons système bombés, pas de tabs Qt 90s.
- Light et dark mode rendus correctement, switch sans relancer.
- L'indicateur VAD pulse visiblement en écoute, fixe sinon. Timer session lisible.
- Le chat Live respire (marges, line-height, partial bubble distinct).
- Aucune régression fonctionnelle (auto-scroll, badge non-lu, génération de résumé, copier/révéler).
- Démarre et tourne sans warnings PyObjC ni Qt.
