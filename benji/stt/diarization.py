"""Lightweight pitch-based speaker labeling.

Not a real diarization system — estimates median fundamental frequency (F0)
of a segment via autocorrelation, then clusters into up to 2 speakers based
on a rolling baseline. Good enough for two-speaker recordings with
clearly different voices (e.g. male/female).
"""

from __future__ import annotations

import numpy as np


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
