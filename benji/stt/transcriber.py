import time
from collections import deque
from queue import Queue

import numpy as np

from benji.config import STTConfig
from benji.history import TranscriptionHistory
from benji.stats import SessionStats
from benji.stt.backend import build_backend
from benji.stt.diarization import build_tagger
from benji.stt.postprocessing import is_hallucination, postprocess_text


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

        # Optional diarization (pitch or pyannote)
        self.tagger = (
            build_tagger(
                self.config.diarization_backend,
                max_speakers=self.config.diarization_max_speakers,
            )
            if self.config.diarization
            else None
        )

        print(f"[STT] Loading Whisper model '{self.config.model_size}'...")
        self.backend = build_backend(
            model_size=self.config.model_size,
            beam_size=self.config.beam_size,
            cpu_threads=self.config.cpu_threads,
            compute_type=self.config.compute_type,
        )
        print("[STT] Model loaded")

    def warmup(self, seconds: float = 1.0) -> None:
        """Run a one-shot inference on silence to amortize JIT/graph compilation.

        Without this, the first real utterance pays the compile cost and feels laggy.
        """
        try:
            n = int(seconds * self.sample_rate)
            silence = np.zeros(n, dtype=np.float32)
            t0 = time.monotonic()
            for _ in self.backend.transcribe(
                silence, language=self.config.language, beam_size=1, initial_prompt=None
            ):
                pass
            print(f"[STT] Warm-up done in {(time.monotonic() - t0) * 1000:.0f} ms")
        except Exception as e:
            print(f"[STT] Warm-up skipped: {e}")

    def _initial_prompt(self) -> str | None:
        """Build initial_prompt = glossary terms + recent context words.

        Glossary biases Whisper toward correct spellings of proper nouns / domain
        terms; sliding context smooths transitions between segments.
        """
        parts: list[str] = []
        if self.config.glossary:
            parts.append(", ".join(self.config.glossary) + ".")
        if self._context:
            parts.append(" ".join(self._context))
        if not parts:
            return None
        return " ".join(parts)

    def _apply_agc(self, audio: np.ndarray) -> np.ndarray:
        """Peak-normalize quiet audio so Whisper sees a consistent level.

        Boost-only: only quiet segments are scaled up; loud segments pass through.
        Avoids amplifying near-silence (peak < 0.01) which would just amplify noise.
        """
        target = self.config.agc_target_peak
        if target <= 0.0 or audio.size == 0:
            return audio
        peak = float(np.max(np.abs(audio)))
        if peak < 0.01 or peak >= self.config.agc_min_peak:
            return audio
        gain = min(target / peak, 8.0)  # Cap gain at 8x to limit noise blow-up
        return (audio * gain).astype(np.float32, copy=False)

    def _run_segment(self, audio: np.ndarray, is_final: bool):
        start_t = time.monotonic()
        audio = self._apply_agc(audio)
        self.display_queue.put({"type": "segment_start"})
        beam = self.config.beam_size if is_final else self.config.partial_beam_size
        words: list[dict] = []
        for word in self.backend.transcribe(
            audio,
            language=self.config.language,
            beam_size=beam,
            initial_prompt=self._initial_prompt(),
        ):
            words.append(word)
            # Forward the full dict (text + timestamps) to the overlay.
            self.display_queue.put({
                "type": "word",
                "text": word["text"],
                "start": word.get("start"),
                "end": word.get("end"),
            })

        if not is_final:
            if self.stats is not None and words:
                latency_ms = (time.monotonic() - start_t) * 1000
                audio_seconds = len(audio) / self.sample_rate
                self.stats.record_segment(audio_seconds, latency_ms, is_final=False)
            return
        if not words:
            return

        full_text = postprocess_text(
            " ".join(w["text"] for w in words), language=self.config.language
        )
        if is_hallucination(full_text):
            # Tell the overlay to drop the streamed (hallucinated) words instead
            # of leaving them on screen.
            self.display_queue.put({"type": "final_text", "text": "", "drop": True})
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

        # Replace the streamed (raw) overlay text with the post-processed/corrected one.
        self.display_queue.put({"type": "final_text", "text": full_text})

        print(f'[STT] "{full_text}"')
        self.history.add(full_text)

        # Update sliding context from the raw (pre-label) words
        for w in words[-self.config.context_words:]:
            self._context.append(w["text"])

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
