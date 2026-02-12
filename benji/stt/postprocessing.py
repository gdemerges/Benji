"""Post-processing utilities to enhance Whisper transcriptions."""

import re


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

    # Remove common hesitations/fillers
    hesitations = [
        r'\b(euh|euuh|heu|heuu)\b',  # French
        r'\b(uh|uhh|um|umm|hmm|huh)\b',  # English
        r'\b(eh|ah|oh)\b',  # General
    ]
    for pattern in hesitations:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Fix spacing around punctuation
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)  # Remove space before punctuation
    text = re.sub(r'([,.!?;:])\s*', r'\1 ', text)  # Add space after punctuation
    text = re.sub(r'\s+', ' ', text)  # Remove multiple spaces

    # Capitalize first letter
    text = text.strip()
    if text:
        text = text[0].upper() + text[1:]

    # Capitalize after sentence-ending punctuation
    def capitalize_after_period(match):
        return match.group(1) + match.group(2).upper()

    text = re.sub(r'([.!?])\s+([a-z])', capitalize_after_period, text)

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

    # Ensure sentence ends with punctuation
    if text and text[-1] not in '.!?':
        text += '.'

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
