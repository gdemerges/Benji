"""Session summarizer using MLX-LM (Apple Silicon)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

MODEL_ID = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"


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
                f"Transcription :\n{transcription_text}"
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


def summarize(entries: list[dict]) -> str | None:
    """Generate a summary of a transcription session using MLX-LM."""
    if not entries:
        print("[Summary] Aucune transcription à résumer.")
        return None

    transcription_text = "\n".join(e["text"] for e in entries)
    if len(transcription_text.strip()) < 50:
        print("[Summary] Transcription trop courte pour être résumée.")
        return None

    try:
        from mlx_lm import load, generate
    except ImportError:
        print("[Summary] mlx-lm non installé. Exécute : pip install mlx-lm")
        return None

    print(f"[Summary] Chargement du modèle '{MODEL_ID}'...")
    print("[Summary] (Le premier lancement télécharge le modèle, ~800MB)")

    model, tokenizer = load(MODEL_ID)

    print("[Summary] Génération du résumé...")
    prompt = _build_prompt(tokenizer, transcription_text)
    summary = generate(model, tokenizer, prompt=prompt, max_tokens=512, verbose=False)

    return summary.strip()


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

    return file_path
