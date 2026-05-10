"""Session summarizer using MLX-LM (Apple Silicon)."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Callable

MODEL_ID = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

# Cache the loaded MLX-LM model across calls — first load is ~1-2s, subsequent
# summaries reuse the same weights.
_MODEL_CACHE: dict = {}


def _get_model():
    if "model" not in _MODEL_CACHE:
        from mlx_lm import load
        print(f"[Summary] Chargement du modèle '{MODEL_ID}'...")
        print("[Summary] (Le premier lancement télécharge le modèle, ~800MB)")
        model, tokenizer = load(MODEL_ID)
        _MODEL_CACHE["model"] = model
        _MODEL_CACHE["tokenizer"] = tokenizer
    return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]


def _build_prompt(tokenizer, transcription_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "Tu es un assistant qui résume des conversations. Réponds uniquement en français, de façon concise et structurée.",
        },
        {
            "role": "user",
            "content": (
                "Voici la transcription d'une conversation. "
                "Génère un résumé structuré avec :\n"
                "- **Sujets abordés** : les thèmes principaux\n"
                "- **Points clés** : les informations importantes\n"
                "- **Décisions / Actions** : les décisions prises ou actions à faire (si applicable)\n\n"
                "Sois factuel et concis. "
                "Si la transcription est trop courte pour être résumée, dis-le simplement.\n\n"
                "Transcription :\n<transcription>\n"
                f"{transcription_text}"
                "\n</transcription>"
            ),
        },
    ]

    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    # Fallback for tokenizers without chat template
    return f"Résume cette conversation en français :\n\n{transcription_text}\n\nRésumé :"


def summarize(
    entries: list[dict],
    on_token: Callable[[str], None] | None = None,
) -> str | None:
    """Generate a summary of a transcription session using MLX-LM.

    If `on_token` is provided, streams the output token-by-token via
    `mlx_lm.stream_generate` and calls the callback for each chunk.
    Returns the full summary text once generation completes.
    """
    if not entries:
        print("[Summary] Aucune transcription à résumer.")
        return None

    transcription_text = "\n".join(e["text"] for e in entries)
    if len(transcription_text.strip()) < 50:
        print("[Summary] Transcription trop courte pour être résumée.")
        return None

    try:
        from mlx_lm import generate, stream_generate
    except ImportError:
        print("[Summary] mlx-lm non installé. Exécute : pip install mlx-lm")
        return None

    model, tokenizer = _get_model()

    print("[Summary] Génération du résumé...")
    prompt = _build_prompt(tokenizer, transcription_text)

    if on_token is None:
        return generate(model, tokenizer, prompt=prompt, max_tokens=512, verbose=False).strip()

    chunks: list[str] = []
    for response in stream_generate(model, tokenizer, prompt=prompt, max_tokens=512):
        # mlx_lm.stream_generate yields a `GenerationResponse` with a `.text` field
        # (incremental text since the previous yield).
        piece = getattr(response, "text", None) or str(response)
        if piece:
            chunks.append(piece)
            try:
                on_token(piece)
            except Exception as e:
                print(f"[Summary] on_token callback failed: {e}")
    return "".join(chunks).strip()


def save_summary(summary: str) -> Path:
    """Save the summary to a timestamped markdown file."""
    cache_dir = Path.home() / ".cache" / "benji" / "summaries"
    cache_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now()
    filename = f"summary_{timestamp.strftime('%Y%m%d_%H%M%S')}.md"
    file_path = cache_dir / filename

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# Résumé de session — {timestamp.strftime('%d/%m/%Y %H:%M')}\n\n")
        f.write(summary)
        f.write("\n")
    os.chmod(file_path, 0o600)

    return file_path
