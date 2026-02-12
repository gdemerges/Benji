import platform

import numpy as np
from faster_whisper import WhisperModel
from queue import Queue

from benji.config import STTConfig
from benji.history import TranscriptionHistory
from benji.stt.postprocessing import postprocess_text


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
        self.history = TranscriptionHistory()

        # Auto-detect device if not specified
        self.device, self.compute_type = _detect_device()
        if self.config.compute_type != "auto":
            self.compute_type = self.config.compute_type

        # Pre-load model immediately to avoid delay on first transcription
        self.model = None
        self.load_model()

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
        """Transcribe and send words progressively to display queue (real-time preview)."""
        # Signal start of new segment
        self.display_queue.put({"type": "segment_start"})

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

        # Stream words in real-time as they're transcribed
        full_text = []
        for segment in segments:
            if hasattr(segment, 'words') and segment.words:
                for word in segment.words:
                    word_text = word.word.strip()
                    full_text.append(word_text)
                    # Send word immediately for real-time preview
                    self.display_queue.put({"type": "word", "text": word_text})

        # Save full text to history with post-processing
        if full_text:
            full_text_str = " ".join(full_text)
            # Apply post-processing for better punctuation/capitalization
            processed_text = postprocess_text(full_text_str, language=self.config.language)
            print(f"[STT] \"{processed_text}\"")
            self.history.add(processed_text)

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
        print("[STT] Transcription started (streaming mode)")
        while True:
            audio = self.transcribe_queue.get()
            if audio is None:
                break
            self.transcribe_segment_streaming(audio)
        print("[STT] Transcription stopped")
