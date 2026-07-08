# benji/stt/

- `backend.py` — sélectionne faster-whisper ou mlx-whisper selon la plateforme et la config
- `transcriber.py` — consomme `transcribe_queue`, stream les mots vers `display_queue`. Utilise une fenêtre de contexte glissante (`STTConfig.context_words`) comme `initial_prompt`.
- `diarization.py` — labellisation de locuteurs (activée par défaut). Backend `pyannote` (embeddings, N locuteurs, modèle HF **gated** → accepter les conditions sur hf.co/pyannote/embedding) avec fallback automatique sur `pitch` (F0, A/B) si indisponible. Le label voyage comme champ `speaker` dans le message `final_text` (jamais collé au texte) — la couleur par locuteur vient de `benji.ui.style.speaker_color`.
- `postprocessing.py` — nettoyage grammaire/ponctuation appliqué après la passe finale

Passes partielles : `beam_size=1` (vitesse). Passes finales : `beam_size=5` (qualité).
