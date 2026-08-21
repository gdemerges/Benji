# Benji

macOS real-time transcription app. Pipeline: mic → VAD → STT → subtitle overlay.

## Rules

- Python 3.12, PyQt6, **Apple Silicon exclusivement** (mlx). No mypy, no type stubs. Le repli CPU faster-whisper a été retiré avec Whisper : sans Apple Silicon, Benji ne transcrit plus en local.
- Dependency management: **uv** (`pyproject.toml` is source of truth). `uv sync` to install, `uv run benji` to launch.
- Tunable config lives in `benji/config.py` (dataclasses), not config files. A few operational/secret settings are read from env vars instead: `BENJI_LAUNCH_MODE`, `BENJI_LOG_LEVEL`, `BENJI_VIBRANCY`, `HF_TOKEN`/`HUGGINGFACE_HUB_TOKEN` (diarization), `ANTHROPIC_API_KEY` (cloud summary), `BENJI_SENTRY_DSN` + `BENJI_ENV` (crash reporting, inactif sans DSN), `BENJI_SUPPORT_EMAIL` (destinataire du « Signaler un problème », défaut = adresse perso).
- **Confidentialité — règle non négociable** : Benji transcrit des réunions. Rien de ce qui sort de la machine (log fichier, rapport de bug, événement Sentry) ne doit contenir de texte transcrit, de glossaire, de chemin d'historique ni de jeton. Les transcriptions sont logguées en **DEBUG** uniquement ; `benji/monitoring.py` et `benji/report.py` scrubbent le reste. Des tests verrouillent ces trois canaux — ne les contourne pas.
- Three inter-thread queues: `audio_queue` → `transcribe_queue` → `display_queue`. Never block the Qt thread. Avec `AudioConfig.system_audio`, un `AudioMixer` s'intercale en amont d'`audio_queue` (micro + audio système) — cf. `benji/audio/CLAUDE.md`.
- **Le backend (`backend/`) est GELÉ** depuis le 2026-08-19 : le produit se positionne en achat unique, 100 % local. Ne pas passer Stripe en live, ne pas implémenter `/v1/history`, ne pas migrer vers Postgres tant que des utilisateurs payants ne réclament pas la sync. Le code reste en place — cf. le bandeau dans `backend/README.md`.
- **Données utilisateur** : historique, résumés, `meetings.json` et identifiants vivent sous `~/Library/Application Support/Benji` (`benji/paths.py`), pas dans `~/.cache` — qui ne garde que les poids de modèles. Ne jamais résoudre ces chemins à l'import : `tests/conftest.py` isole `HOME`, un chemin figé irait déplacer les vraies données de l'utilisateur.
- **Une réunion est une entité de premier ordre** (`benji/meetings.py`) : chaque entrée d'historique porte son identifiant, et l'export / le résumé / l'effacement s'y cantonnent. Les entrées d'avant cette notion sont regroupées sous `meetings.LEGACY_ID`.
- **Direction visuelle** : une seule couleur saturée (le rouge d'enregistrement, jamais pour une action), trois voix typographiques (SF Pro pour l'app, New York pour les paroles transcrites, SF Mono pour le temps), et la ligne de temps du transcript comme élément signature. Toute couleur vit dans `benji/ui/style.py` — cf. `benji/ui/CLAUDE.md`.
- **Un seul moteur local : Parakeet TDT.** Whisper a été retiré (mlx-whisper et faster-whisper) : sur des tampons de 1 à 8 s, il encode toujours une fenêtre paddée de 30 s là où Parakeet ne paie que l'audio reçu — 58 ms contre ~680 ms mesurés. Sont partis avec lui le glossaire et le contexte glissant (`initial_prompt` n'existe plus), et le choix de taille de modèle. Ne pas les réintroduire sans revenir sur ce compromis. Détails dans `benji/stt/CLAUDE.md`.
- `STTConfig.language` defaults to `"fr"`. Keep French in mind when touching STT logic.
- macOS: accessory policy must be set before `QApplication()` — see `benji/main.py:9`.
- Run: `uv run benji`. Tests: `uv run pytest`.

## Vault Obsidian

Le suivi de ce projet est documenté dans : `/Users/guillaumedemerges/Documents/Life/wiki/projects/Benji`

Notes du vault : `Benji.md` (fiche principale, état d'avancement) + `Benji-Architecture.md`, `Benji-Backend-Cloud.md`, `Benji-Distribution.md`.

**Règle** : à la fin d'une session de travail significative (feature terminée, architecture changée, checklist publication avancée), mets à jour la note concernée avec les changements. Garde le format existant (frontmatter, sections, checkboxes cochées/décochées).

## Modules

- [benji/](benji/CLAUDE.md) — core package, entry point, config, history, stats
- [benji/audio/](benji/audio/CLAUDE.md) — mic capture + Silero VAD
- [benji/stt/](benji/stt/CLAUDE.md) — Whisper transcription, diarization, post-processing
- [benji/ui/](benji/ui/CLAUDE.md) — PyQt6 overlay, tray, history window, live summary
