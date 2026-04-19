import threading
import time

import numpy as np
import sounddevice as sd
from queue import Queue

from benji.config import AudioConfig


class AudioCapture:
    """Microphone capture with automatic reconnection on device changes."""

    def __init__(self, audio_queue: Queue, config: AudioConfig = None):
        self.config = config or AudioConfig()
        self.audio_queue = audio_queue
        self.stream: sd.InputStream | None = None
        self._stop = threading.Event()
        self._watchdog: threading.Thread | None = None
        self._lock = threading.Lock()

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        if status:
            # Non-fatal (overflow, underflow); log at most
            print(f"[AudioCapture] {status}")
        self.audio_queue.put(indata[:, 0].copy())

    def _open_stream(self) -> bool:
        try:
            stream = sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=self.config.dtype,
                blocksize=self.config.chunk_size,
                callback=self._callback,
            )
            stream.start()
            with self._lock:
                self.stream = stream
            device_info = sd.query_devices(kind="input")
            name = device_info.get("name", "?") if isinstance(device_info, dict) else "?"
            print(f"[AudioCapture] Recording at {self.config.sample_rate}Hz on '{name}'")
            return True
        except Exception as e:
            print(f"[AudioCapture] Failed to open stream: {e}")
            return False

    def _close_stream(self):
        with self._lock:
            if self.stream is not None:
                try:
                    self.stream.stop()
                    self.stream.close()
                except Exception:
                    pass
                self.stream = None

    def _watchdog_loop(self):
        """Poll stream health and reopen if the device disappears."""
        while not self._stop.is_set():
            time.sleep(1.0)
            with self._lock:
                active = self.stream is not None and self.stream.active
            if active:
                continue
            print("[AudioCapture] Device lost — attempting reconnect...")
            self._close_stream()
            # Let sounddevice refresh its device list
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                pass
            # Retry with exponential backoff (capped)
            delay = 0.5
            while not self._stop.is_set():
                if self._open_stream():
                    break
                time.sleep(delay)
                delay = min(delay * 2, 5.0)

    def start(self):
        if not self._open_stream():
            raise RuntimeError("Could not open audio input stream")
        self._watchdog = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="AudioWatchdog"
        )
        self._watchdog.start()

    def stop(self):
        self._stop.set()
        self._close_stream()
        print("[AudioCapture] Stopped")
