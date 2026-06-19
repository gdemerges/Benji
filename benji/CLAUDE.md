# benji/ — Core package

`main.py` est le point d'entrée : il instancie les configs, crée les trois queues, démarre les threads VAD + STT, puis lance la boucle Qt.

`config.py` contient tous les paramètres sous forme de dataclasses (`AudioConfig`, `VADConfig`, `STTConfig`, `UIConfig`). La taille du modèle Whisper est auto-sélectionnée au démarrage selon RAM/GPU.

`history.py` + `stats.py` reçoivent chaque utterance finale pour persister l'historique et les métriques de session.

`billing.py` — client Stripe côté app : appelle le backend authentifié (`/v1/billing/checkout`, `/v1/billing/portal`) et ouvre l'URL renvoyée dans le navigateur. Aucune clé Stripe sur le poste. Câblé au menu tray.
