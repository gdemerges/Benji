import platform

import numpy as np
from faster_whisper import WhisperModel
from queue import Queue

from benji.config import STTConfig
from benji.history import TranscriptionHistory


def _detect_device():
    """Auto-detect best available device for inference."""
    # Check for CUDA (NVIDIA GPU)
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass

    # Check for MPS (Apple Silicon GPU)
    if platform.system() == "Darwin":
        try:
            import torch
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                # Note: faster-whisper doesn't support MPS yet, fall back to CPU
                # but use int8 for better performance on Apple Silicon
                return "cpu", "int8"
        except ImportError:
            pass

    # Default to CPU with auto compute type
    return "cpu", "auto"


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
        self.history = TranscriptionHistory()

        # Auto-detect device if not specified
        self.device, self.compute_type = _detect_device()
        if self.config.compute_type != "auto":
            self.compute_type = self.config.compute_type

    def load_model(self):
        # Check if model is already cached
        from faster_whisper.utils import download_model
        try:
            model_path = download_model(self.config.model_size, local_files_only=True)
        except Exception:
            model_path = None
            print(f"[STT] Model '{self.config.model_size}' not found locally. Downloading (this may take several minutes)...")
            self.display_queue.put({"type": "segment_start"})
            self.display_queue.put({"type": "word", "text": f"Downloading model '{self.config.model_size}'..."})

        print(f"[STT] Loading Whisper model '{self.config.model_size}' on {self.device} ({self.compute_type})...")
        self.model = WhisperModel(
            model_path or self.config.model_size,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.config.cpu_threads if self.device == "cpu" else None,
        )
        print(f"[STT] Model loaded")

    def transcribe_segment_streaming(self, audio: np.ndarray):
        """Transcribe and send words progressively to display queue."""
        segments, info = self.model.transcribe(
            audio,
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=False,
            word_timestamps=True,  # Enable word-level timestamps
            condition_on_previous_text=True,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
        )

        # Collect all words with timestamps
        all_words = []
        full_text = []
        for segment in segments:
            if hasattr(segment, 'words') and segment.words:
                for word in segment.words:
                    all_words.append(word)
                    full_text.append(word.word.strip())

        if not all_words:
            return

        # Signal start of new segment
        self.display_queue.put({"type": "segment_start"})

        # Send words progressively - instant display for maximum fluidity
        for word in all_words:
            self.display_queue.put({"type": "word", "text": word.word.strip()})

        # Save full text to history
        full_text_str = " ".join(full_text)
        print(f"[STT] \"{full_text_str}\"")
        self.history.add(full_text_str)

    def transcribe_segment_classic(self, audio: np.ndarray) -> str:
        """Classic mode: transcribe and send complete text at once."""
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
        full_text = " ".join(text_parts).strip()

        if full_text and not full_text.isspace():
            print(f"[STT] \"{full_text}\"")
            self.history.add(full_text)
            self.display_queue.put(full_text)

    def run(self):
        self.load_model()
        print("[STT] Transcription started (streaming mode)")
        while True:
            audio = self.transcribe_queue.get()
            if audio is None:
                break
            self.transcribe_segment_streaming(audio)
        print("[STT] Transcription stopped")
