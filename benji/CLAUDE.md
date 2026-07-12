# benji/ — Core package

`main.py` est un point d'entrée mince : logging, politique « accessory » macOS (avant tout import Qt), puis délègue à `BenjiApplication`.

`app.py` est le **composition root** : la classe `BenjiApplication` porte l'état et découpe le démarrage/arrêt en phases (`_build_configs`, `_build_account`, `_build_pipeline`, `_create_qapp`, `_load_transcriber`, `_start_stt`, `_build_display`, `_build_windows`, `_build_tray_and_shortcuts`, `shutdown`). Les cinq configs sont regroupées dans `AppConfigs` (injectable → les phases non-Qt sont testables sans lancer l'app, cf. `tests/test_app_composition.py`).

`config.py` contient tous les paramètres sous forme de dataclasses (`AudioConfig`, `VADConfig`, `STTConfig`, `UIConfig`). La taille du modèle Whisper est auto-sélectionnée au démarrage selon RAM/GPU.

`history.py` + `stats.py` reçoivent chaque utterance finale pour persister l'historique et les métriques de session.

`export.py` — rendu pur (sans Qt) des entrées d'historique vers `txt` / `md` / `srt`, avec renommage optionnel des locuteurs (`speaker_names`). Le SRT dérive les bornes de temps des horodatages (fin d'un segment = début du suivant, durée estimée pour le dernier). Câblé aux boutons Copier/Exporter de `history_window`.

`account.py` — compte Benji côté app : `Session` (login/register/refresh auto) + persistance des jetons dans `~/.cache/benji/credentials.json` (0600). L'abonnement suit le **compte**, pas le poste → mêmes identifiants = même plan sur toute plateforme. Au démarrage, `main.py` injecte l'access token dans `LLMConfig.backend_token`.

`billing.py` — client Stripe côté app : appelle le backend authentifié (`/v1/billing/checkout`, `/v1/billing/portal`) et ouvre l'URL renvoyée dans le navigateur. Aucune clé Stripe sur le poste. Câblé au menu tray (token fourni par la `Session`).
