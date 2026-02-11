import torch
import numpy as np
from queue import Queue, Full

from benji.config import AudioConfig, VADConfig


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

        # Load Silero VAD
        self.model, _ = torch.hub.load(
            "snakers4/silero-vad", "silero_vad", trust_repo=True
        )
        self.model.eval()
        print("[VAD] Silero VAD loaded")

        # State
        self.is_speaking = False
        self.speech_buffer: list[np.ndarray] = []
        self.silence_chunks = 0
        self.pre_speech_buffer: list[np.ndarray] = []

    def _chunk_duration_ms(self, chunk: np.ndarray) -> float:
        return len(chunk) / self.sample_rate * 1000

    def process_chunk(self, chunk: np.ndarray) -> None:
        tensor = torch.from_numpy(chunk)
        confidence = self.model(tensor, self.sample_rate).item()

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

    def run(self):
        print("[VAD] Processing started")
        while True:
            chunk = self.audio_queue.get()
            if chunk is None:
                break
            self.process_chunk(chunk)
        print("[VAD] Processing stopped")
