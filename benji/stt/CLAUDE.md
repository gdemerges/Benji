# benji/stt/

- `backend.py` — sélectionne le moteur : **Whisper** (mlx-whisper sur Apple Silicon, faster-whisper ailleurs) ou **Parakeet** (`STTConfig.stt_provider = "parakeet"`, **le défaut** — dépendance dure sur macOS). Tout moteur indisponible retombe sur Whisper : un choix de moteur ne doit jamais empêcher de transcrire.

  **Pourquoi Parakeet change tout ici** : Whisper encode toujours une fenêtre paddée de **30 s**, quelle que soit la durée réelle du tampon ; Parakeet ne paie que l'audio reçu. Mesuré sur M4 Pro avec les tampons de Benji — tampon de 1,2 s : **58 ms contre ~680 ms** pour whisper-medium ; 6,7 s : 126 ms contre ~800 ms. Mémoire équivalente (2,3 vs 2,2 Go de pic MLX). C'est aussi pour ça que `large-v3-turbo` est un piège ici : son encodeur est celui de large-v3, il est **2 à 2,7× plus lent que medium** sur ce régime malgré sa réputation de rapidité en long-form.

  **Ce que Parakeet coûte** : aucun conditionnement par le texte → `STTConfig.glossary` et le contexte glissant sont sans effet (averti une fois au démarrage, et dit dans les Préférences). Poids sous **CC-BY-4.0** : attribution NVIDIA due si distribué.

  **Alimenté en mémoire** : l'API publique de `parakeet-mlx` ne transcrit que des chemins de fichiers ; on passe par `get_logmel()` + `generate()`. Écrire les tampons d'une réunion dans un fichier temporaire serait une régression de confidentialité — et ça évite au passage la dépendance à ffmpeg. Ne pas « simplifier » vers `model.transcribe(path)`.

  **Sous-mots** : Parakeet rend des morceaux de mots (`" c"`, `"ô"`, `"té"`), recollés par `group_tokens_into_words()` — **par phrase** (`words_from_result`) et non sur les tokens aplatis, sinon la fin d'une phrase se colle au début de la suivante (« Apple.Ça »).
- `transcriber.py` — consomme `transcribe_queue`, stream les mots vers `display_queue`. Utilise une fenêtre de contexte glissante (`STTConfig.context_words`) comme `initial_prompt`. Si `llm_correction` est activé, le texte brut est affiché immédiatement puis corrigé sur un thread dédié (`STT-corrector`) : chaque final porte un `seq` que l'overlay utilise pour remplacer le bon segment (et ignorer une correction dont le segment n'est plus à l'écran).
- `diarization.py` — labellisation de locuteurs (activée par défaut). Le tagger ne dépend que de l'audio : il tourne **en parallèle** de la passe finale (pool à un worker, `_await_speaker` avec timeout) au lieu d'ajouter son coût au délai d'affichage. Un tagger bloqué rend un segment sans locuteur, jamais un thread STT figé. Backend `pyannote` (embeddings, N locuteurs, modèle HF **gated** → accepter les conditions sur hf.co/pyannote/embedding) avec fallback automatique sur `pitch` (F0, A/B) si indisponible. Le label voyage comme champ `speaker` dans le message `final_text` (jamais collé au texte) — la couleur par locuteur vient de `benji.ui.style.speaker_color`.
- `postprocessing.py` — nettoyage grammaire/ponctuation appliqué après la passe finale

Passes partielles : `beam_size=1` (vitesse). Passes finales : `beam_size=5` (qualité).
