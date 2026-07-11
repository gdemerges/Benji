import logging
import queue
import threading
import time
from queue import Queue

import numpy as np
import sounddevice as sd

from benji.config import AudioConfig

log = logging.getLogger(__name__)

# Throttle for "audio_queue full" warnings: log the first drop, then at most
# one warning every N seconds (the CoreAudio callback fires ~30x/s).
_DROP_LOG_INTERVAL_S = 5.0


class AudioCapture:
    """Microphone capture with automatic reconnection on device changes."""

    def __init__(self, audio_queue: Queue, config: AudioConfig = None, stats=None):
        self.config = config or AudioConfig()
        self.audio_queue = audio_queue
        self.stats = stats  # benji.stats.SessionStats (optional)
        self.stream: sd.InputStream | None = None
        self._stop = threading.Event()
        self._watchdog: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_drop_log = 0.0

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        # IMPORTANT: never block here — this runs on the CoreAudio/PortAudio
        # realtime thread. If the consumer stalls, drop the chunk instead.
        if status:
            # Non-fatal (overflow, underflow); log at most
            log.warning("%s", status)
        try:
            self.audio_queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            if self.stats is not None:
                self.stats.record_drop("audio_queue_full")
            now = time.monotonic()
            if now - self._last_drop_log >= _DROP_LOG_INTERVAL_S:
                self._last_drop_log = now
                log.warning("audio_queue full — dropping audio chunks")

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
            log.info("Recording at %dHz on '%s'", self.config.sample_rate, name)
            return True
        except Exception as e:
            log.error("Failed to open stream: %s", e)
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
            log.warning("Device lost — attempting reconnect...")
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
        log.info("Stopped")
