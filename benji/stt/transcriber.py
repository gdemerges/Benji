from queue import Queue

import numpy as np

from benji.config import STTConfig
from benji.history import TranscriptionHistory
from benji.stt.backend import build_backend
from benji.stt.postprocessing import postprocess_text


# Known Whisper hallucination patterns (training-data artifacts)
_HALLUCINATION_PATTERNS = [
    "sous-titres réalisés par",
    "sous-titres fait par",
    "merci d'avoir regardé",
    "merci de votre attention",
    "thanks for watching",
    "thank you for watching",
]


def _is_hallucination(text: str) -> bool:
    normalized = text.lower().strip().rstrip(".")
    return any(pattern in normalized for pattern in _HALLUCINATION_PATTERNS)


class Transcriber:
    def __init__(
        self,
        transcribe_queue: Queue,
        display_queue: Queue,
        config: STTConfig = None,
    ):
        self.transcribe_queue = transcribe_queue
        self.display_queue = display_queue
        self.config = config or STTConfig()
        self.history = TranscriptionHistory()

        print(f"[STT] Loading Whisper model '{self.config.model_size}'...")
        self.backend = build_backend(
            model_size=self.config.model_size,
            beam_size=self.config.beam_size,
            cpu_threads=self.config.cpu_threads,
        )
        print("[STT] Model loaded")

    def _run_segment(self, audio: np.ndarray, is_final: bool):
        self.display_queue.put({"type": "segment_start"})
        words: list[str] = []
        for word_text in self.backend.transcribe(audio, language=self.config.language):
            words.append(word_text)
            self.display_queue.put({"type": "word", "text": word_text})

        if not is_final or not words:
            return

        full_text = postprocess_text(" ".join(words), language=self.config.language)
        if _is_hallucination(full_text):
            return
        print(f'[STT] "{full_text}"')
        self.history.add(full_text)

    def run(self):
        print("[STT] Transcription started (incremental streaming)")
        while True:
            item = self.transcribe_queue.get()
            if item is None:
                break
            audio = item["audio"]
            is_final = item["is_final"]
            # Drop stale partials if a newer item is already queued
            if not is_final and not self.transcribe_queue.empty():
                continue
            self._run_segment(audio, is_final)
        print("[STT] Transcription stopped")
