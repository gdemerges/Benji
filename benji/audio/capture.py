import sounddevice as sd
import numpy as np
from queue import Queue

from benji.config import AudioConfig


class AudioCapture:
    def __init__(self, audio_queue: Queue, config: AudioConfig = None):
        self.config = config or AudioConfig()
        self.audio_queue = audio_queue
        self.stream = None

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"[AudioCapture] {status}")
        self.audio_queue.put(indata[:, 0].copy())

    def start(self):
        self.stream = sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            blocksize=self.config.chunk_size,
            callback=self._callback,
        )
        self.stream.start()
        print(f"[AudioCapture] Recording at {self.config.sample_rate}Hz")

    def stop(self):
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            print("[AudioCapture] Stopped")
