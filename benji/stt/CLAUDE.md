# benji/stt/

- `backend.py` — **deux moteurs, un par type de passe**, parce qu'elles n'ont pas le même cahier des charges.

  | | passes partielles | passe finale |
  |---|---|---|
  | moteur | Parakeet TDT | Whisper (mlx-whisper) |
  | ce qu'on optimise | la latence | la justesse de ce qui reste |
  | coût mesuré | ~50 ms | ~800 ms |
  | langue | détection auto | **`fr` forcé** |

  **Pourquoi Whisper est revenu sur le final.** Parakeet fait de la détection automatique sur 25 langues et **n'offre aucun levier pour la forcer** — confirmé par la fiche NVIDIA, et `parakeet-mlx` n'a pas une seule occurrence de « language » dans son code. Sur des segments difficiles il bascule en anglais : au milieu d'une réunion française on récupère « Enwiten ne se content plus de relier the utility devient also the chef d'orchestre ». Whisper accepte `language="fr"` : la dérive devient impossible. Le texte partiel étant de toute façon remplacé par le final, l'arbitrage est net — vitesse là où le texte est jetable, garantie là où il est conservé (historique, exports, résumés).

  Ce compromis **ne se voit pas sur de l'audio de synthèse**, trop propre pour faire dériver la détection. Il faut de la vraie parole pour l'observer : s'en souvenir avant de conclure quoi que ce soit d'un banc d'essai TTS.

  `STTConfig.final_engine="parakeet"` réutilise le moteur des partielles pour le final : ~5× plus rapide, sans garantie de langue. Le glossaire et le contexte glissant restent absents des deux chemins (`initial_prompt` a été retiré avec l'ancien pipeline).

  **Piège MLX — le modèle appartient au thread qui l'a chargé.** MLX charge paresseusement et lie les tableaux au **stream du thread qui les évalue en premier**. `ParakeetBackend.__init__` appelle donc `mx.eval(model.parameters())` pour matérialiser les poids sur place ; sans ça la liaison n'aurait lieu qu'au premier décodage réel et l'inférence depuis le thread STT lèverait « There is no Stream(gpu, N) in current thread ». `warmup()` ne peut pas jouer ce rôle : il préchauffe sur du silence, dont Parakeet ne décode aucun token. Et le chargement doit se faire sur un thread qui **vit aussi longtemps que l'app** — d'où `_load_transcriber` sur le thread principal dans `app.py`. Chargé depuis un thread éphémère, Parakeet devient **définitivement** inutilisable, sans réparation possible par `mx.new_stream()`.

  **Alimenté en mémoire** : l'API publique de `parakeet-mlx` ne transcrit que des chemins de fichiers ; on passe par `get_logmel()` + `generate()`. Écrire les tampons d'une réunion dans un fichier temporaire serait une régression de confidentialité — et ça évite la dépendance à ffmpeg. Ne pas « simplifier » vers `model.transcribe(path)`.

  **Sous-mots** : Parakeet rend des morceaux de mots (`" c"`, `"ô"`, `"té"`), recollés par `group_tokens_into_words()` — **par phrase** (`words_from_result`), sinon la fin d'une phrase se colle au début de la suivante (« Apple.Ça »).

- `transcriber.py` — consomme `transcribe_queue`, stream les mots vers `display_queue`. Chaque passe partielle re-décode le tampon **entier** via Parakeet (~123 ms pour 8 s) et fige le préfixe sur lequel deux passes successives s'accordent (LocalAgreement-2) ; le figeage est **monotone**, un mot affiché n'est jamais repris. La passe finale passe par Whisper (langue forcée) : c'est ce texte-là qui est conservé. Si `llm_correction` est activé, le texte brut est affiché immédiatement puis corrigé sur un thread dédié (`STT-corrector`) : chaque final porte un `seq` que l'overlay utilise pour remplacer le bon segment (et ignorer une correction dont le segment n'est plus à l'écran).
- `diarization.py` — labellisation de locuteurs (activée par défaut). Le tagger ne dépend que de l'audio : il tourne **en parallèle** de la passe finale (pool à un worker, `_await_speaker` avec timeout) au lieu d'ajouter son coût au délai d'affichage. Un tagger bloqué rend un segment sans locuteur, jamais un thread STT figé. Backend `pyannote` (embeddings, N locuteurs, modèle HF **gated** → accepter les conditions sur hf.co/pyannote/embedding) avec fallback automatique sur `pitch` (F0, A/B) si indisponible. Le label voyage comme champ `speaker` dans le message `final_text` (jamais collé au texte) — la couleur par locuteur vient de `benji.ui.style.speaker_color`.
- `postprocessing.py` — nettoyage grammaire/ponctuation appliqué après la passe finale

`VADConfig.partial_growth_factor` est à 0 (cadence fixe) : le frein progressif protégeait du coût de Whisper et ne faisait plus que rendre le direct poussif.
