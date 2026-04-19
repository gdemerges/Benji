import time
from collections import deque
from queue import Queue

import numpy as np

from benji.config import STTConfig
from benji.history import TranscriptionHistory
from benji.stats import SessionStats
from benji.stt.backend import build_backend
from benji.stt.diarization import SpeakerTagger
from benji.stt.postprocessing import postprocess_text


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
        stats: SessionStats | None = None,
        sample_rate: int = 16000,
    ):
        self.transcribe_queue = transcribe_queue
        self.display_queue = display_queue
        self.config = config or STTConfig()
        self.history = TranscriptionHistory()
        self.stats = stats
        self.sample_rate = sample_rate

        # Sliding context: last N validated words injected as initial_prompt
        self._context = deque(maxlen=self.config.context_words)

        # Optional diarization
        self.tagger = SpeakerTagger() if self.config.diarization else None

        print(f"[STT] Loading Whisper model '{self.config.model_size}'...")
        self.backend = build_backend(
            model_size=self.config.model_size,
            beam_size=self.config.beam_size,
            cpu_threads=self.config.cpu_threads,
        )
        print("[STT] Model loaded")

    def _initial_prompt(self) -> str | None:
        if not self._context:
            return None
        return " ".join(self._context)

    def _run_segment(self, audio: np.ndarray, is_final: bool):
        start_t = time.monotonic()
        self.display_queue.put({"type": "segment_start"})
        beam = self.config.beam_size if is_final else self.config.partial_beam_size
        words: list[str] = []
        for word_text in self.backend.transcribe(
            audio,
            language=self.config.language,
            beam_size=beam,
            initial_prompt=self._initial_prompt(),
        ):
            words.append(word_text)
            self.display_queue.put({"type": "word", "text": word_text})

        if not is_final or not words:
            return

        full_text = postprocess_text(" ".join(words), language=self.config.language)
        if _is_hallucination(full_text):
            return

        # Speaker label (best-effort, pitch-based)
        if self.tagger is not None:
            label = self.tagger.label(audio, self.sample_rate)
            if label:
                full_text = f"{label}: {full_text}"

        # Optional LLM correction (synchronous; only if enabled)
        if self.config.llm_correction:
            try:
                from benji.llm.corrector import correct
                full_text = correct(full_text, language=self.config.language)
            except Exception as e:
                print(f"[STT] LLM correction skipped: {e}")

        print(f'[STT] "{full_text}"')
        self.history.add(full_text)

        # Update sliding context from the raw (pre-label) words
        for w in words[-self.config.context_words:]:
            self._context.append(w)

        # Stats
        if self.stats is not None:
            latency_ms = (time.monotonic() - start_t) * 1000
            audio_seconds = len(audio) / self.sample_rate
            self.stats.record_segment(audio_seconds, latency_ms)

    def run(self):
        print("[STT] Transcription started (incremental streaming)")
        while True:
            item = self.transcribe_queue.get()
            if item is None:
                break
            audio = item["audio"]
            is_final = item["is_final"]
            if not is_final and not self.transcribe_queue.empty():
                continue
            self._run_segment(audio, is_final)
        print("[STT] Transcription stopped")
