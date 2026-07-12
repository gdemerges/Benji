"""Session summarizer using MLX-LM (Apple Silicon)."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

MODEL_ID = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"

# Cache the loaded MLX-LM model across calls — first load is ~1-2s, subsequent
# summaries reuse the same weights.
_MODEL_CACHE: dict = {}


def _get_model():
    if "model" not in _MODEL_CACHE:
        from mlx_lm import load
        log.info("Chargement du modèle '%s'...", MODEL_ID)
        log.info("(Le premier lancement télécharge le modèle, ~800MB)")
        model, tokenizer = load(MODEL_ID)
        _MODEL_CACHE["model"] = model
        _MODEL_CACHE["tokenizer"] = tokenizer
    return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"]


# Source unique de vérité du prompt, partagée par le provider local (mlx-lm) et
# le provider cloud (Claude) — voir benji/llm/providers.py.
SYSTEM_PROMPT = (
    "Tu es un assistant qui résume des conversations. "
    "Réponds uniquement en français, de façon concise et structurée."
)


def build_user_prompt(transcription_text: str) -> str:
    return (
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
    )


def prepare_transcription(entries: list[dict]) -> str | None:
    """Concatène les utterances et écarte les sessions trop courtes.

    Retourne le texte prêt à résumer, ou None si rien d'exploitable.
    """
    if not entries:
        log.info("Aucune transcription à résumer.")
        return None
    transcription_text = "\n".join(e["text"] for e in entries)
    if len(transcription_text.strip()) < 50:
        log.info("Transcription trop courte pour être résumée.")
        return None
    return transcription_text


def _build_prompt(tokenizer, transcription_text: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(transcription_text)},
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
    transcription_text = prepare_transcription(entries)
    if transcription_text is None:
        return None

    try:
        from mlx_lm import generate, stream_generate
    except ImportError:
        log.warning("mlx-lm non installé. Exécute : uv sync")
        return None

    model, tokenizer = _get_model()

    log.info("Génération du résumé...")
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
                log.warning("on_token callback failed: %s", e)
    return "".join(chunks).strip()


def save_summary(summary: str) -> Path:
    """Save the summary to a timestamped markdown file."""
    cache_dir = Path.home() / ".cache" / "benji" / "summaries"
    cache_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now()
    filename = f"summary_{timestamp.strftime('%Y%m%d_%H%M%S')}.md"
    file_path = cache_dir / filename

    # Mode 0600 dès la création (un write-puis-chmod laisserait le résumé
    # lisible par tous entre les deux appels).
    fd = os.open(file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"# Résumé de session — {timestamp.strftime('%d/%m/%Y %H:%M')}\n\n")
        f.write(summary)
        f.write("\n")

    return file_path
