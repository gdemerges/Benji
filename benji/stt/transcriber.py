import logging
import time
from collections import deque
from queue import Queue

import numpy as np

from benji.config import STTConfig

log = logging.getLogger(__name__)
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

        # Per-segment streaming state (LocalAgreement-2 over partials).
        # We don't re-transcribe the whole buffer every time: we slice off the
        # audio prefix whose words have been confirmed by two successive partials
        # and inject the confirmed text as initial_prompt. This bounds partial
        # cost to roughly the unconfirmed tail length.
        self._committed_words: list[dict] = []
        self._committed_samples: int = 0
        self._prev_tail_texts: list[str] = []

        # Optional diarization (pitch or pyannote)
        self.tagger = (
            build_tagger(
                self.config.diarization_backend,
                max_speakers=self.config.diarization_max_speakers,
            )
            if self.config.diarization
            else None
        )

        log.info("Loading Whisper model '%s'...", self.config.model_size)
        self.backend = build_backend(
            model_size=self.config.model_size,
            beam_size=self.config.beam_size,
            cpu_threads=self.config.cpu_threads,
            compute_type=self.config.compute_type,
        )
        log.info("Model loaded")

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
            log.info("Warm-up done in %.0f ms", (time.monotonic() - t0) * 1000)
        except Exception as e:
            log.warning("Warm-up skipped: %s", e)

    def _reset_partial_state(self) -> None:
        self._committed_words = []
        self._committed_samples = 0
        self._prev_tail_texts = []

    @staticmethod
    def _norm(text: str) -> str:
        """Normalize a word for cross-partial agreement comparison.

        Whisper sometimes flips capitalization or attaches/detaches punctuation
        between passes; ignore those so the agreement check focuses on the
        actual lexical content.
        """
        return text.strip().lower().strip(".,;:!?\"'«»()[]")

    @staticmethod
    def _common_prefix_len(a: list[str], b: list[str]) -> int:
        n = min(len(a), len(b))
        for i in range(n):
            if a[i] != b[i]:
                return i
        return n

    def _initial_prompt(self, extra_committed: list[str] | None = None) -> str | None:
        """Build initial_prompt = glossary + recent context + in-segment committed words.

        Glossary biases Whisper toward correct spellings of proper nouns / domain
        terms; sliding context smooths transitions between segments; the
        per-segment committed prefix lets a sliced (delta) partial decode pick
        up where the previous partial left off.
        """
        parts: list[str] = []
        if self.config.glossary:
            parts.append(", ".join(self.config.glossary) + ".")
        if self._context:
            parts.append(" ".join(self._context))
        if extra_committed:
            parts.append(" ".join(extra_committed))
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

    def _run_partial(self, audio: np.ndarray) -> None:
        """Re-transcribe only the unconfirmed tail and stabilize via LocalAgreement-2.

        Cost is bounded by the tail length, not the full segment, so a long
        utterance no longer pays O(n²) in partials.
        """
        start_t = time.monotonic()
        audio = self._apply_agc(audio)

        # Skip if the new tail is too short to be worth a decode pass.
        min_tail_samples = int(0.3 * self.sample_rate)
        if len(audio) - self._committed_samples < min_tail_samples:
            return

        slice_audio = audio[self._committed_samples:]
        slice_offset_s = self._committed_samples / self.sample_rate

        committed_texts = [w["text"] for w in self._committed_words]
        prompt = self._initial_prompt(extra_committed=committed_texts)

        new_words: list[dict] = []
        for w in self.backend.transcribe(
            slice_audio,
            language=self.config.language,
            beam_size=self.config.partial_beam_size,
            initial_prompt=prompt,
        ):
            new_words.append(w)

        # LocalAgreement-2: the prefix that matches the previous partial's
        # unconfirmed tail is considered stable and gets committed.
        new_texts_norm = [self._norm(w["text"]) for w in new_words]
        agree_n = self._common_prefix_len(new_texts_norm, self._prev_tail_texts)

        newly_committed = new_words[:agree_n]
        for w in newly_committed:
            shifted = dict(w)
            if w.get("start") is not None:
                shifted["start"] = w["start"] + slice_offset_s
            if w.get("end") is not None:
                shifted["end"] = w["end"] + slice_offset_s
            self._committed_words.append(shifted)

        # Advance the audio cut point past the last committed word so the next
        # partial decodes a shorter slice. Only safe when end timestamps exist.
        if newly_committed and newly_committed[-1].get("end") is not None:
            advance = int(newly_committed[-1]["end"] * self.sample_rate)
            self._committed_samples += max(0, advance)

        self._prev_tail_texts = new_texts_norm[agree_n:]

        # Redraw the full live snapshot: stable prefix + best-guess tail.
        self.display_queue.put({"type": "segment_start"})
        for w in self._committed_words:
            self.display_queue.put({
                "type": "word", "text": w["text"],
                "start": w.get("start"), "end": w.get("end"),
            })
        for w in new_words[agree_n:]:
            shifted_start = (w["start"] + slice_offset_s) if w.get("start") is not None else None
            shifted_end = (w["end"] + slice_offset_s) if w.get("end") is not None else None
            self.display_queue.put({
                "type": "word", "text": w["text"],
                "start": shifted_start, "end": shifted_end,
            })

        if self.stats is not None and new_words:
            latency_ms = (time.monotonic() - start_t) * 1000
            self.stats.record_segment(len(slice_audio) / self.sample_rate, latency_ms, is_final=False)

    def _run_segment(self, audio: np.ndarray, is_final: bool):
        if not is_final:
            self._run_partial(audio)
            return

        start_t = time.monotonic()
        audio = self._apply_agc(audio)
        self.display_queue.put({"type": "segment_start"})
        words: list[dict] = []
        for word in self.backend.transcribe(
            audio,
            language=self.config.language,
            beam_size=self.config.beam_size,
            initial_prompt=self._initial_prompt(),
        ):
            words.append(word)
            self.display_queue.put({
                "type": "word",
                "text": word["text"],
                "start": word.get("start"),
                "end": word.get("end"),
            })

        if not words:
            self._reset_partial_state()
            return

        full_text = postprocess_text(
            " ".join(w["text"] for w in words), language=self.config.language
        )
        if is_hallucination(full_text):
            # Tell the overlay to drop the streamed (hallucinated) words instead
            # of leaving them on screen.
            self.display_queue.put({"type": "final_text", "text": "", "drop": True})
            self._reset_partial_state()
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
                log.warning("LLM correction skipped: %s", e)

        # Replace the streamed (raw) overlay text with the post-processed/corrected one.
        self.display_queue.put({"type": "final_text", "text": full_text})

        log.info('"%s"', full_text)
        self.history.add(full_text)

        # Update sliding context from the raw (pre-label) words
        for w in words[-self.config.context_words:]:
            self._context.append(w["text"])

        # Stats
        if self.stats is not None:
            latency_ms = (time.monotonic() - start_t) * 1000
            audio_seconds = len(audio) / self.sample_rate
            self.stats.record_segment(audio_seconds, latency_ms)

        # Final closes the segment — partial state resets for the next utterance.
        self._reset_partial_state()

    def run(self):
        log.info("Transcription started (incremental streaming)")
        while True:
            item = self.transcribe_queue.get()
            if item is None:
                break
            audio = item["audio"]
            is_final = item["is_final"]
            if not is_final and not self.transcribe_queue.empty():
                continue
            try:
                self._run_segment(audio, is_final)
            except Exception:
                # A single bad segment should not kill the STT loop.
                log.exception("STT segment failed (final=%s, %.2fs); skipping",
                              is_final, len(audio) / self.sample_rate)
                if self.stats is not None:
                    self.stats.record_drop("stt_error")
                # Ensure the overlay doesn't keep partial words from a failed segment.
                try:
                    self.display_queue.put({"type": "final_text", "text": "", "drop": True})
                except Exception:
                    pass
                # Reset streaming state so the next segment starts clean.
                self._reset_partial_state()
        log.info("Transcription stopped")
