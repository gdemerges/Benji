import os

import numpy as np
import onnxruntime as ort
from queue import Queue, Full

from benji.config import AudioConfig, VADConfig

SILERO_ONNX_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"


class SileroVADOnnx:
    """Silero VAD using ONNX runtime (no PyTorch dependency)."""

    def __init__(self, model_path: str):
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.session = ort.InferenceSession(model_path, sess_options=opts)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(64, dtype=np.float32)  # 64 samples context for 16kHz
        self._sr = np.array(16000, dtype=np.int64)

    def reset_state(self):
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._context = np.zeros(64, dtype=np.float32)

    def __call__(self, audio_chunk: np.ndarray) -> float:
        # Prepend context to audio chunk
        audio_with_context = np.concatenate([self._context, audio_chunk])
        # Update context for next call
        self._context = audio_chunk[-64:]
        # Run inference
        ort_inputs = {
            "input": audio_with_context[np.newaxis, :].astype(np.float32),
            "state": self._state,
            "sr": self._sr,
        }
        out, new_state = self.session.run(None, ort_inputs)
        self._state = new_state
        return float(out[0][0])


def _download_model() -> str:
    cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "benji")
    os.makedirs(cache_dir, exist_ok=True)
    model_path = os.path.join(cache_dir, "silero_vad.onnx")
    if not os.path.exists(model_path):
        print("[VAD] Downloading Silero VAD ONNX model...")
        import httpx
        with httpx.stream("GET", SILERO_ONNX_URL, follow_redirects=True) as r:
            r.raise_for_status()
            with open(model_path, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
    return model_path


class VADProcessor:
    def __init__(
        self,
        audio_queue: Queue,
        transcribe_queue: Queue,
        audio_config: AudioConfig = None,
        vad_config: VADConfig = None,
    ):
        self.audio_queue = audio_queue
        self.transcribe_queue = transcribe_queue
        self.audio_config = audio_config or AudioConfig()
        self.config = vad_config or VADConfig()
        self.sample_rate = self.audio_config.sample_rate

        # Load Silero VAD (ONNX)
        model_path = _download_model()
        self.model = SileroVADOnnx(model_path)
        print("[VAD] Silero VAD loaded (ONNX)")

        # State
        self.is_speaking = False
        self.speech_buffer: list[np.ndarray] = []
        self.silence_chunks = 0
        self.pre_speech_buffer: list[np.ndarray] = []

    def _chunk_duration_ms(self, chunk: np.ndarray) -> float:
        return len(chunk) / self.sample_rate * 1000

    def process_chunk(self, chunk: np.ndarray) -> None:
        confidence = self.model(chunk)

        chunk_ms = self._chunk_duration_ms(chunk)

        if confidence >= self.config.speech_threshold:
            if not self.is_speaking:
                self.is_speaking = True
                self.speech_buffer = list(self.pre_speech_buffer)
                print("[VAD] Speech started")
            self.speech_buffer.append(chunk)
            self.silence_chunks = 0
        else:
            if self.is_speaking:
                self.speech_buffer.append(chunk)
                self.silence_chunks += 1
                silence_ms = self.silence_chunks * chunk_ms

                if silence_ms >= self.config.silence_duration_ms:
                    self._flush_segment()
            else:
                self.pre_speech_buffer.append(chunk)
                max_pre = int(self.config.pre_speech_pad_ms / chunk_ms)
                if len(self.pre_speech_buffer) > max_pre:
                    self.pre_speech_buffer.pop(0)

        # Force flush long utterances
        if self.is_speaking:
            total_samples = sum(len(c) for c in self.speech_buffer)
            if total_samples / self.sample_rate >= self.config.max_speech_duration_s:
                self._flush_segment()

    def _flush_segment(self):
        audio = np.concatenate(self.speech_buffer)
        min_samples = int(self.config.min_speech_duration_ms / 1000 * self.sample_rate)

        if len(audio) >= min_samples:
            duration = len(audio) / self.sample_rate
            print(f"[VAD] Speech segment: {duration:.1f}s")
            try:
                self.transcribe_queue.put(audio, block=False)
            except Full:
                print("[VAD] Transcribe queue full, dropping segment")

        self.speech_buffer = []
        self.silence_chunks = 0
        self.is_speaking = False
        self.pre_speech_buffer = []
        self.model.reset_state()

    def run(self):
        print("[VAD] Processing started")
        while True:
            chunk = self.audio_queue.get()
            if chunk is None:
                break
            self.process_chunk(chunk)
        print("[VAD] Processing stopped")
