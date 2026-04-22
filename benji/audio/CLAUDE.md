# benji/audio/

- `capture.py` — sounddevice InputStream → `audio_queue` (float32, 16 kHz, mono, chunks de 512 samples)
- `vad.py` — Silero VAD via ONNX (graph entièrement optimisé). Accumule les frames de parole, flush vers `transcribe_queue` sur silence. Envoie `VAD_START`/`VAD_END` dans `display_queue` pour l'indicateur UI. Re-transcription partielle toutes les `VADConfig.partial_interval_ms` ms.

La taille de chunk est fixée à 512 samples — contrainte du modèle Silero ONNX.
