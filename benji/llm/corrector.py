"""Post-hoc text correction via MLX-LM (punctuation, grammar).

Loads the model lazily on first call. Falls back to returning the input
text unchanged on any error. Runs synchronously in the transcriber thread,
so keep the model small (~1B params) to stay under ~500ms per segment.
"""

from __future__ import annotations

import threading

MODEL_ID = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

_lock = threading.Lock()
_model = None
_tokenizer = None
_load_failed = False


def _ensure_loaded() -> bool:
    global _model, _tokenizer, _load_failed
    if _load_failed:
        return False
    if _model is not None:
        return True
    with _lock:
        if _model is not None:
            return True
        try:
            from mlx_lm import load
            print(f"[Corrector] Loading {MODEL_ID}...")
            _model, _tokenizer = load(MODEL_ID)
            print("[Corrector] Ready")
            return True
        except Exception as e:
            print(f"[Corrector] Disabled ({e})")
            _load_failed = True
            return False


def correct(text: str, language: str | None = "fr") -> str:
    """Return a lightly corrected version of *text*, or *text* unchanged on error."""
    if not text or len(text.strip()) < 3:
        return text
    if not _ensure_loaded():
        return text

    try:
        from mlx_lm import generate
        lang = "français" if language in (None, "fr") else language
        messages = [
            {
                "role": "system",
                "content": (
                    f"Tu corriges des transcriptions vocales en {lang}. "
                    "Corrige UNIQUEMENT la ponctuation, les majuscules et les fautes "
                    "d'accord évidentes. Ne reformule JAMAIS. Réponds avec le texte corrigé seul, sans commentaire."
                ),
            },
            {"role": "user", "content": text},
        ]
        prompt = _tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        output = generate(_model, _tokenizer, prompt=prompt, max_tokens=len(text) + 50, verbose=False)
        corrected = output.strip().strip('"').strip()
        # Safety: reject if the model invented a much longer response
        if not corrected or len(corrected) > 2 * len(text) + 40:
            return text
        return corrected
    except Exception as e:
        print(f"[Corrector] Skipped: {e}")
        return text
