"""Rendu des transcriptions vers des formats exportables (txt / md / srt).

Fonctions pures : elles prennent la liste d'entrées de `TranscriptionHistory`
(dicts `{"timestamp", "text", "speaker"?}`) et renvoient une chaîne. Aucun accès
disque, aucune dépendance Qt → directement testable.

`speaker_names` est une table de correspondance optionnelle label → nom lisible
(ex. `{"A": "Alice"}`) appliquée au rendu ; les labels absents sont laissés tels
quels.
"""

from __future__ import annotations

from datetime import datetime

SUPPORTED_FORMATS = ("txt", "md", "srt")

# Vitesse de lecture approximative (caractères/seconde) pour estimer la durée
# d'un sous-titre quand aucune borne de fin n'est disponible.
_CHARS_PER_SECOND = 15.0
_MIN_SUBTITLE_SECONDS = 1.5


def _display_speaker(entry: dict, speaker_names: dict[str, str] | None) -> str | None:
    speaker = entry.get("speaker")
    if not speaker:
        return None
    if speaker_names and speaker in speaker_names and speaker_names[speaker].strip():
        return speaker_names[speaker].strip()
    return speaker


def distinct_speakers(entries: list[dict]) -> list[str]:
    """Labels de locuteurs présents dans les entrées, dans l'ordre d'apparition."""
    seen: list[str] = []
    for entry in entries:
        speaker = entry.get("speaker")
        if speaker and speaker not in seen:
            seen.append(speaker)
    return seen


def _sorted_with_text(entries: list[dict]) -> list[dict]:
    """Entrées non vides, triées chronologiquement (robuste à l'ordre d'entrée)."""
    kept = [e for e in entries if e.get("text", "").strip()]

    def key(entry: dict) -> datetime:
        try:
            return datetime.fromisoformat(entry["timestamp"])
        except (KeyError, ValueError, TypeError):
            return datetime.min

    return sorted(kept, key=key)


def to_txt(entries: list[dict], speaker_names: dict[str, str] | None = None) -> str:
    """Texte brut : `[YYYY-MM-DD HH:MM:SS] Locuteur : texte` par ligne."""
    lines = []
    for entry in _sorted_with_text(entries):
        try:
            ts = datetime.fromisoformat(entry["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            prefix = f"[{ts}] "
        except (KeyError, ValueError, TypeError):
            prefix = ""
        speaker = _display_speaker(entry, speaker_names)
        who = f"{speaker} : " if speaker else ""
        lines.append(f"{prefix}{who}{entry['text'].strip()}")
    return "\n".join(lines) + ("\n" if lines else "")


def to_markdown(entries: list[dict], speaker_names: dict[str, str] | None = None) -> str:
    """Markdown : titre daté puis un paragraphe horodaté par utterance."""
    rows = _sorted_with_text(entries)
    if not rows:
        return "# Transcription\n\n_Aucune transcription._\n"

    try:
        day = datetime.fromisoformat(rows[0]["timestamp"]).strftime("%Y-%m-%d")
        title = f"# Transcription — {day}"
    except (KeyError, ValueError, TypeError):
        title = "# Transcription"

    blocks = [title, ""]
    for entry in rows:
        try:
            clock = datetime.fromisoformat(entry["timestamp"]).strftime("%H:%M:%S")
            meta = f"`{clock}`"
        except (KeyError, ValueError, TypeError):
            meta = ""
        speaker = _display_speaker(entry, speaker_names)
        if speaker:
            meta = f"{meta} · **{speaker}**" if meta else f"**{speaker}**"
        if meta:
            blocks.append(meta + "  ")  # deux espaces = saut de ligne markdown
        blocks.append(entry["text"].strip())
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


def _srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms_total = int(round(seconds * 1000))
    hours, ms_total = divmod(ms_total, 3_600_000)
    minutes, ms_total = divmod(ms_total, 60_000)
    secs, millis = divmod(ms_total, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _estimated_duration(text: str) -> float:
    return max(_MIN_SUBTITLE_SECONDS, len(text) / _CHARS_PER_SECOND)


def to_srt(entries: list[dict], speaker_names: dict[str, str] | None = None) -> str:
    """Sous-titres SRT. Les bornes de temps sont dérivées des horodatages :
    fin d'un segment = début du suivant (ou durée estimée pour le dernier)."""
    rows = _sorted_with_text(entries)
    if not rows:
        return ""

    try:
        times = [datetime.fromisoformat(e["timestamp"]) for e in rows]
    except (KeyError, ValueError, TypeError):
        return ""
    base = times[0]

    blocks = []
    for i, entry in enumerate(rows):
        start = (times[i] - base).total_seconds()
        if i + 1 < len(rows):
            end = (times[i + 1] - base).total_seconds()
        else:
            end = start + _estimated_duration(entry["text"])
        if end <= start:
            end = start + _estimated_duration(entry["text"])
        speaker = _display_speaker(entry, speaker_names)
        text = f"{speaker}: {entry['text'].strip()}" if speaker else entry["text"].strip()
        blocks.append(
            f"{i + 1}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text}"
        )
    return "\n\n".join(blocks) + "\n"


_RENDERERS = {
    "txt": to_txt,
    "md": to_markdown,
    "srt": to_srt,
}


def render(entries: list[dict], fmt: str, speaker_names: dict[str, str] | None = None) -> str:
    """Rend les entrées dans le format demandé (`txt` / `md` / `srt`)."""
    try:
        renderer = _RENDERERS[fmt]
    except KeyError:
        raise ValueError(f"Format d'export inconnu : {fmt!r}") from None
    return renderer(entries, speaker_names)
