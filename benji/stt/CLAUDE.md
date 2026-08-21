# benji/stt/

- `backend.py` — **un seul moteur : Parakeet TDT** (`mlx-community/parakeet-tdt-0.6b-v3`). Whisper (mlx-whisper *et* faster-whisper) a été retiré : sur des tampons de 1 à 8 s re-décodés souvent, il encode toujours une fenêtre **paddée de 30 s** quand Parakeet ne paie que l'audio reçu — 58 ms contre ~680 ms sur un tampon de 1,2 s, à mémoire équivalente. Corollaire : plus de repli CPU, Benji est Apple Silicon exclusivement.

  **Ce qui est parti avec Whisper** : `initial_prompt`, donc le **glossaire** et le contexte glissant — Parakeet n'accepte aucun conditionnement par le texte. Et le choix de taille de modèle : il n'y en a qu'un.

  **Piège MLX — le modèle appartient au thread qui l'a chargé.** MLX charge paresseusement et lie les tableaux au **stream du thread qui les évalue en premier**. `ParakeetBackend.__init__` appelle donc `mx.eval(model.parameters())` pour matérialiser les poids sur place ; sans ça la liaison n'aurait lieu qu'au premier décodage réel et l'inférence depuis le thread STT lèverait « There is no Stream(gpu, N) in current thread ». `warmup()` ne peut pas jouer ce rôle : il préchauffe sur du silence, dont Parakeet ne décode aucun token. Et le chargement doit se faire sur un thread qui **vit aussi longtemps que l'app** — d'où `_load_transcriber` sur le thread principal dans `app.py` (~1,4 s de splash figé). Chargé depuis un thread éphémère, Parakeet devient **définitivement** inutilisable, sans réparation possible par `mx.new_stream()`.

  **Alimenté en mémoire** : l'API publique de `parakeet-mlx` ne transcrit que des chemins de fichiers ; on passe par `get_logmel()` + `generate()`. Écrire les tampons d'une réunion dans un fichier temporaire serait une régression de confidentialité — et ça évite la dépendance à ffmpeg. Ne pas « simplifier » vers `model.transcribe(path)`.

  **Sous-mots** : Parakeet rend des morceaux de mots (`" c"`, `"ô"`, `"té"`), recollés par `group_tokens_into_words()` — **par phrase** (`words_from_result`), sinon la fin d'une phrase se colle au début de la suivante (« Apple.Ça »).

- `diarization.py` — labellisation de locuteurs (activée par défaut). Le tagger ne dépend que de l'audio : il tourne **en parallèle** de la passe finale (pool à un worker, `_await_speaker` avec timeout) au lieu d'ajouter son coût au délai d'affichage. Un tagger bloqué rend un segment sans locuteur, jamais un thread STT figé. Backend `pyannote` (embeddings, N locuteurs, modèle HF **gated** → accepter les conditions sur hf.co/pyannote/embedding) avec fallback automatique sur `pitch` (F0, A/B) si indisponible. Le label voyage comme champ `speaker` dans le message `final_text` (jamais collé au texte) — la couleur par locuteur vient de `benji.ui.style.speaker_color`.
- `postprocessing.py` — nettoyage grammaire/ponctuation appliqué après la passe finale

`VADConfig.partial_growth_factor` est à 0 (cadence fixe) : le frein progressif protégeait du coût de Whisper et ne faisait plus que rendre le direct poussif.
