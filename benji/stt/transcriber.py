import numpy as np
from faster_whisper import WhisperModel
from queue import Queue

from benji.config import STTConfig


class Transcriber:
    def __init__(
        self,
        transcribe_queue: Queue,
        display_queue: Queue,
        config: STTConfig = None,
    ):
        self.transcribe_queue = transcribe_queue
        self.display_queue = display_queue
        self.config = config or STTConfig()
        self.model = None

    def load_model(self):
        print(f"[STT] Loading Whisper model '{self.config.model_size}'...")
        self.model = WhisperModel(
            self.config.model_size,
            device="cpu",
            compute_type=self.config.compute_type,
            cpu_threads=self.config.cpu_threads,
        )
        print(f"[STT] Model loaded")

    def transcribe_segment(self, audio: np.ndarray) -> str:
        segments, info = self.model.transcribe(
            audio,
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=False,
            word_timestamps=False,
            condition_on_previous_text=True,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
        )
        text_parts = [seg.text for seg in segments]
        return " ".join(text_parts).strip()

    def run(self):
        self.load_model()
        print("[STT] Transcription started")
        while True:
            audio = self.transcribe_queue.get()
            if audio is None:
                break
            text = self.transcribe_segment(audio)
            if text and not text.isspace():
                print(f"[STT] \"{text}\"")
                self.display_queue.put(text)
        print("[STT] Transcription stopped")
