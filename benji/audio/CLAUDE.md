# benji/audio/

- `capture.py` — sounddevice InputStream → `audio_queue` (float32, 16 kHz, mono, chunks de 512 samples). Le callback ne bloque jamais (drop si queue pleine). `pause()`/`resume()` ferment/rouvrent réellement le stream (indicateur micro macOS éteint pendant la pause) ; le watchdog ne reconnecte pas tant que la pause est active.
- `loopback.py` — détection du périphérique de boucle (BlackHole, Loopback…) qui porte l'audio système. Module **pur** : reçoit une liste de périphériques au format `sd.query_devices()`, ne touche jamais sounddevice → testable sans matériel. Un périphérique appartenant à une app (Teams, Zoom) n'est jamais auto-sélectionné : il ne capterait que cette app.
- `system_capture.py` — `SystemAudioCapture` (2e InputStream sur la boucle, downmix mono + ré-échantillonnage vers 16 kHz) et `AudioMixer` (somme micro + système vers `audio_queue`). **Le micro donne l'horloge** : pour chaque chunk micro de N samples on consomme N samples système, complétés par du silence si retard. La cadence en sortie reste celle du micro, donc le VAD garde ses chunks de 512. Saturation (pas de normalisation) au mixage, sinon le seuil adaptatif du VAD lirait le pompage de niveau comme du bruit. Échec d'ouverture = non fatal, repli micro seul.
- `vad.py` — Silero VAD via ONNX (graph entièrement optimisé). Accumule les frames de parole, flush vers `transcribe_queue` sur silence. Envoie `VAD_START`/`VAD_END` dans `display_queue` pour l'indicateur UI. Re-transcription partielle toutes les `VADConfig.partial_interval_ms` ms.

La taille de chunk est fixée à 512 samples — contrainte du modèle Silero ONNX.

Quand `AudioConfig.system_audio` est `False` (défaut), ni `SystemAudioCapture` ni `AudioMixer` ne sont instanciés et `AudioCapture` écrit directement dans `audio_queue` : le chemin micro seul est strictement inchangé. La pause micro arrête aussi la capture système — un voyant micro éteint ne doit jamais laisser croire que plus rien n'est transcrit.
