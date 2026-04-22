# benji/stt/

- `backend.py` — sélectionne faster-whisper ou mlx-whisper selon la plateforme et la config
- `transcriber.py` — consomme `transcribe_queue`, stream les mots vers `display_queue`. Utilise une fenêtre de contexte glissante (`STTConfig.context_words`) comme `initial_prompt`.
- `diarization.py` — labellisation A/B de locuteurs par pitch (optionnel, `STTConfig.diarization`)
- `postprocessing.py` — nettoyage grammaire/ponctuation appliqué après la passe finale

Passes partielles : `beam_size=1` (vitesse). Passes finales : `beam_size=5` (qualité).
