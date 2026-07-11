"""Post-processing utilities to enhance Whisper transcriptions."""

import re

# Common Whisper hallucinations on silence / low-signal audio.
# Matched as substrings against the lower-cased, dot-stripped output.
HALLUCINATION_PATTERNS = (
    "sous-titres réalisés par",
    "sous-titres fait par",
    "sous-titrage st'",
    "sous-titrage société radio",
    "sous-titres faits par",
    "❤️ par sous-titres",
    "amara.org",
    "merci d'avoir regardé",
    "merci de votre attention",
    "merci à tous",
    "abonnez-vous",
    "n'oubliez pas de vous abonner",
    "à la prochaine",
    "thanks for watching",
    "thank you for watching",
    "subscribe to",
    "please subscribe",
    "like and subscribe",
)


def is_hallucination(text: str) -> bool:
    """Return True if *text* looks like a known Whisper hallucination or
    a degenerate repetition (same token >= 4 times in a row)."""
    if not text:
        return True
    normalized = text.lower().strip().rstrip(".!?")
    if any(pattern in normalized for pattern in HALLUCINATION_PATTERNS):
        return True
    # Repetition detector: any word repeated 4+ times in a row → hallucination.
    # Whisper's classic failure mode on noise is to emit the same token in a loop.
    if re.search(r"\b(\w{2,})\b(?:\W+\1\b){3,}", normalized, flags=re.IGNORECASE):
        return True
    return False


def postprocess_text(text: str, language: str = None) -> str:
    """
    Enhance transcription with better punctuation and capitalization.

    Whisper already does basic punctuation, but this improves:
    - Capitalization after periods
    - Removal of hesitations (uh, um, etc.)
    - Proper spacing around punctuation
    - Number formatting
    """
    if not text or not text.strip():
        return text

    # Remove common hesitations/fillers.
    # NB: pas de « eh/ah/oh » ici — mots légitimes en français (« eh bien »,
    # « ah bon »).
    hesitations = [
        r'\b(euh|euuh|heu|heuu)\b',  # French
        r'\b(uh|uhh|um|umm|hmm|huh)\b',  # English
    ]
    for pattern in hesitations:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Fix spacing around punctuation
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)  # Remove space before punctuation
    # Add space after punctuation — sauf entre deux chiffres, pour ne pas
    # casser les nombres (« 2,5 », « 3.14 »).
    text = re.sub(r'((?<!\d)[,.!?;:]|[,.!?;:](?!\d))\s*', r'\1 ', text)

    # Fix French apostrophes (e.g., "qu ' on" -> "qu'on")
    text = re.sub(r"([a-z])\s*'\s*([a-z])", r"\1'\2", text, flags=re.IGNORECASE)

    # Fix hyphens (e.g., "est - ce" -> "est-ce")
    text = re.sub(r"([a-z])\s*-\s*([a-z])", r"\1-\2", text, flags=re.IGNORECASE)

    text = re.sub(r'\s+', ' ', text)  # Remove multiple spaces

    # Ponctuation orpheline en tête après suppression d'une hésitation
    # (« Euh, oui » → « , oui ») : on la retire avant de capitaliser.
    text = re.sub(r'^[\s,;:]+', '', text)

    # Capitalize first letter
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]

    # Capitalize after sentence-ending punctuation (Unicode-aware, preserve space)
    def capitalize_after_period(match):
        return match.group(1) + match.group(2) + match.group(3).upper()

    text = re.sub(r'([.!?])(\s+)(\w)', capitalize_after_period, text, flags=re.UNICODE)

    # Language-specific improvements
    if language == 'en':
        # Capitalize "I" pronoun
        text = re.sub(r'\bi\b', 'I', text)
        # Common contractions
        text = re.sub(r"\bim\b", "I'm", text, flags=re.IGNORECASE)
        text = re.sub(r"\bdont\b", "don't", text, flags=re.IGNORECASE)
        text = re.sub(r"\bcant\b", "can't", text, flags=re.IGNORECASE)

    # Remove trailing spaces
    text = text.strip()

    return text


def format_for_display(text: str) -> str:
    """
    Format text for display (lighter processing, preserves natural flow).
    """
    if not text or not text.strip():
        return text

    # Just clean up spacing
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    return text
