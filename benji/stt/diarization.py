"""Speaker labeling backends.

Two implementations:
- `SpeakerTagger` (pitch): F0 autocorrelation + 2-speaker clustering. No deps,
  works offline on Apple Silicon, but unreliable when voices have similar pitch.
- `PyannoteSpeakerTagger`: pyannote.audio speaker embeddings + cosine clustering.
  Real diarization quality, supports >2 speakers. Requires `pyannote.audio` and
  an HF token (env `HF_TOKEN`) for first-time model download.
"""

from __future__ import annotations

import os
from typing import Protocol

import numpy as np


class DiarizationBackend(Protocol):
    def label(self, audio: np.ndarray, sample_rate: int = 16000) -> str | None: ...


def _estimate_f0(audio: np.ndarray, sample_rate: int = 16000,
                 fmin: float = 70.0, fmax: float = 400.0) -> float | None:
    """Return median F0 estimate in Hz, or None if unvoiced / too short."""
    if len(audio) < sample_rate // 4:  # <250 ms
        return None

    # Take central 1 second to avoid silence at edges
    target_len = min(len(audio), sample_rate)
    start = (len(audio) - target_len) // 2
    segment = audio[start:start + target_len].astype(np.float32)
    segment = segment - segment.mean()
    if np.max(np.abs(segment)) < 1e-3:
        return None

    # Autocorrelation
    corr = np.correlate(segment, segment, mode="full")[len(segment) - 1:]
    min_lag = int(sample_rate / fmax)
    max_lag = int(sample_rate / fmin)
    if max_lag >= len(corr):
        return None
    window = corr[min_lag:max_lag]
    peak = int(np.argmax(window)) + min_lag
    if corr[peak] < 0.3 * corr[0]:  # low periodicity → unvoiced
        return None
    return sample_rate / peak


class SpeakerTagger:
    """Assigns A/B labels based on F0 clustering with a rolling reference."""

    def __init__(self, f0_gap_hz: float = 40.0):
        self.f0_gap_hz = f0_gap_hz
        self._speaker_f0: dict[str, float] = {}
        self._last_label: str | None = None

    def label(self, audio: np.ndarray, sample_rate: int = 16000) -> str | None:
        f0 = _estimate_f0(audio, sample_rate)
        if f0 is None:
            return self._last_label  # fallback to previous speaker

        if not self._speaker_f0:
            self._speaker_f0["A"] = f0
            self._last_label = "A"
            return "A"

        # Find closest existing speaker
        best_label, best_delta = min(
            ((lbl, abs(f0 - ref)) for lbl, ref in self._speaker_f0.items()),
            key=lambda x: x[1],
        )

        if best_delta <= self.f0_gap_hz:
            # Same speaker — update rolling reference (EMA)
            prev = self._speaker_f0[best_label]
            self._speaker_f0[best_label] = 0.8 * prev + 0.2 * f0
            self._last_label = best_label
            return best_label

        # New speaker (cap at 2)
        if len(self._speaker_f0) < 2:
            new_label = "B" if "A" in self._speaker_f0 else "A"
            self._speaker_f0[new_label] = f0
            self._last_label = new_label
            return new_label

        # Already 2 speakers — assign to closest anyway
        self._last_label = best_label
        return best_label


class PyannoteSpeakerTagger:
    """Real speaker labeling using pyannote.audio embeddings + cosine clustering.

    For each segment we compute a 512-d embedding, then assign it to the closest
    existing centroid (cosine sim > threshold) or spawn a new speaker (up to
    `max_speakers`). Centroids update via running mean.
    """

    def __init__(
        self,
        max_speakers: int = 4,
        cosine_threshold: float = 0.55,
        model_id: str = "pyannote/embedding",
    ):
        try:
            from pyannote.audio import Inference
        except ImportError as e:
            raise RuntimeError(
                "pyannote.audio is required for diarization_backend='pyannote'. "
                "Install with: pip install pyannote.audio"
            ) from e

        token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        if not token:
            print("[Diarization] No HF_TOKEN set — pyannote model download may fail")

        # `whole` averages embeddings across the full clip — what we want per segment.
        self._inference = Inference(model_id, window="whole", use_auth_token=token)
        self.max_speakers = max_speakers
        self.cosine_threshold = cosine_threshold
        self._centroids: dict[str, np.ndarray] = {}
        self._counts: dict[str, int] = {}
        self._next_id = 0
        print(f"[Diarization] pyannote.audio loaded ('{model_id}')")

    @staticmethod
    def _cos(a: np.ndarray, b: np.ndarray) -> float:
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        return float(np.dot(a, b) / denom)

    def _new_label(self) -> str:
        # A, B, C, ... up to max_speakers, then numeric.
        if self._next_id < 26:
            label = chr(ord("A") + self._next_id)
        else:
            label = f"S{self._next_id}"
        self._next_id += 1
        return label

    def label(self, audio: np.ndarray, sample_rate: int = 16000) -> str | None:
        if len(audio) < sample_rate // 2:  # <500 ms — too short for stable embedding
            return None
        try:
            # pyannote expects torch tensor with shape (channel, samples)
            import torch
            waveform = torch.from_numpy(audio.astype(np.float32)).unsqueeze(0)
            emb = self._inference({"waveform": waveform, "sample_rate": sample_rate})
            emb = np.asarray(emb).flatten()
        except Exception as e:
            print(f"[Diarization] pyannote inference failed: {e}")
            return None

        if not self._centroids:
            label = self._new_label()
            self._centroids[label] = emb
            self._counts[label] = 1
            return label

        best_label, best_sim = max(
            ((lbl, self._cos(emb, c)) for lbl, c in self._centroids.items()),
            key=lambda x: x[1],
        )

        if best_sim >= self.cosine_threshold or len(self._centroids) >= self.max_speakers:
            n = self._counts[best_label] + 1
            self._centroids[best_label] = self._centroids[best_label] * (n - 1) / n + emb / n
            self._counts[best_label] = n
            return best_label

        label = self._new_label()
        self._centroids[label] = emb
        self._counts[label] = 1
        return label


def build_tagger(backend: str, max_speakers: int = 4) -> DiarizationBackend:
    """Factory: returns a diarization tagger, falling back to pitch on error."""
    if backend == "pyannote":
        try:
            return PyannoteSpeakerTagger(max_speakers=max_speakers)
        except Exception as e:
            print(f"[Diarization] pyannote unavailable ({e}), falling back to pitch")
    return SpeakerTagger()
