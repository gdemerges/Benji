# benji/ — Core package

`main.py` est un point d'entrée mince : logging, Sentry, politique « accessory » macOS (avant tout import Qt), puis délègue à `BenjiApplication`.

## Observabilité

`logging_config.py` — deux handlers : stderr + un `RotatingFileHandler` (2 Mo × 3) vers `log_file_path()` (`~/Library/Logs/Benji/benji.log`). Lancée depuis le Finder, l'app n'a **pas de terminal** : le fichier est le seul canal de diagnostic. Les transcriptions ne sont logguées qu'en DEBUG (le fichier est joint aux rapports de bug).

`monitoring.py` — Sentry, **inactif sans `BENJI_SENTRY_DSN`**. L'essentiel du module est le scrubbing, pas l'init : `include_local_variables=False` (une exception dans `stt/transcriber.py` a le texte de la réunion dans ses locales), breadcrumbs à INFO (donc pas les logs DEBUG), et `_scrub_event` en dernier rempart (jetons, chemin du home).

`report.py` — rendu pur (sans Qt) du `mailto:` de signalement : version, OS, config moteur, `SessionStats`. Aucune donnée personnelle par construction. Câblé au tray (« Signaler un problème… »), qui révèle le log à côté — un `mailto:` ne peut pas porter de pièce jointe.

`app.py` est le **composition root** : la classe `BenjiApplication` porte l'état et découpe le démarrage/arrêt en phases (`_build_configs`, `_build_account`, `_build_pipeline`, `_create_qapp`, `_load_transcriber`, `_start_stt`, `_build_display`, `_build_windows`, `_build_tray_and_shortcuts`, `shutdown`). Les cinq configs sont regroupées dans `AppConfigs` (injectable → les phases non-Qt sont testables sans lancer l'app, cf. `tests/test_app_composition.py`).

`config.py` contient tous les paramètres sous forme de dataclasses (`AudioConfig`, `VADConfig`, `STTConfig`, `UIConfig`). La taille du modèle Whisper est auto-sélectionnée au démarrage selon RAM/GPU.

`history.py` + `stats.py` reçoivent chaque utterance finale pour persister l'historique et les métriques de session.

`export.py` — rendu pur (sans Qt) des entrées d'historique vers `txt` / `md` / `srt`, avec renommage optionnel des locuteurs (`speaker_names`). Le SRT dérive les bornes de temps des horodatages (fin d'un segment = début du suivant, durée estimée pour le dernier). Câblé aux boutons Copier/Exporter de `history_window`.

`account.py` — compte Benji côté app : `Session` (login/register/refresh auto) + persistance des jetons dans `~/.cache/benji/credentials.json` (0600). L'abonnement suit le **compte**, pas le poste → mêmes identifiants = même plan sur toute plateforme. Au démarrage, `main.py` injecte l'access token dans `LLMConfig.backend_token`.

`billing.py` — client Stripe côté app : appelle le backend authentifié (`/v1/billing/checkout`, `/v1/billing/portal`) et ouvre l'URL renvoyée dans le navigateur. Aucune clé Stripe sur le poste. Câblé au menu tray (token fourni par la `Session`).
