"""Titre automatique d'une réunion, à partir de ses premières phrases.

Une réunion s'appelait « Réunion du 21/08 à 14:32 ». C'est un horodatage, pas
un nom : au bout de quinze entrées, la liste ne dit plus rien de ce qu'on y
trouvera, et la recherche par titre n'a aucune prise. Or le modèle local est
déjà chargé pour la correction et le résumé — trois phrases lui suffisent à
proposer « Revue budget T3 ».

Trois principes, tous là pour éviter de piétiner l'utilisateur :

- **On n'écrase jamais un titre choisi par quelqu'un.** La condition de
  déclenchement est que le titre soit *exactement* celui par défaut. Renommer à
  la main, avant ou après, met un point final au débat.
- **On attend d'avoir de quoi juger.** Un titre tiré de « Bonjour, vous
  m'entendez ? » serait pire que l'horodatage.
- **Une seule tentative aboutie par réunion.** Le titre ne se met pas à bouger
  au fil de la conversation ; on nomme, puis on se tait.

Le contenu de la réunion ne quitte pas la machine : le modèle est local
(mlx-lm). Le titre produit n'est pas loggué — c'est du contenu de réunion.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable

from benji import meetings
from benji.history import TranscriptionHistory

log = logging.getLogger(__name__)

# En deçà, il n'y a rien à nommer : on laisse l'horodatage.
MIN_CHARS = 300
# Au-delà, on n'apprend plus rien de plus sur le sujet et on paie du contexte.
MAX_CHARS = 1500
MAX_TITLE_CHARS = 60

SYSTEM_PROMPT = (
    "Tu nommes des réunions. Réponds par un titre court en français, "
    "trois à six mots, sans ponctuation finale, sans guillemets, "
    "sans phrase d'introduction. Rien d'autre que le titre."
)


def build_prompt(transcription_text: str) -> str:
    return (
        "Voici le début d'une réunion. Donne-lui un titre court qui dit son sujet.\n\n"
        "<transcription>\n"
        f"{transcription_text[:MAX_CHARS]}"
        "\n</transcription>"
    )


def clean_title(raw: str) -> str:
    """Ramène la sortie du modèle à un titre utilisable, ou à une chaîne vide.

    Un petit modèle répond volontiers « Titre : "Revue budget T3". » ou ajoute
    une phrase d'explication : on ne garde que la première ligne, débarrassée de
    son préambule et de ses guillemets. Une sortie qui n'y survit pas est
    rejetée — garder l'horodatage vaut mieux qu'un titre absurde.
    """
    line = (raw or "").strip().splitlines()[0] if (raw or "").strip() else ""
    line = re.sub(r"^\s*(titre|title)\s*[:\-–]\s*", "", line, flags=re.IGNORECASE)
    # En boucle : « "Revue budget T3". » a le point *après* le guillemet, un
    # seul passage laisserait l'un ou l'autre.
    previous = None
    while line != previous:
        previous = line
        line = line.strip().strip("\"'«»").rstrip(".!?,;:").strip()
    line = re.sub(r"\s+", " ", line)
    if len(line) > MAX_TITLE_CHARS:
        line = line[:MAX_TITLE_CHARS].rsplit(" ", 1)[0].strip()
    # Un mot seul ne nomme pas une réunion ; un « titre » très long est une
    # phrase, donc le modèle a répondu à côté.
    if len(line) < 3 or len(line.split()) < 2:
        return ""
    return line


def needs_title(meeting, entries: list[dict], min_chars: int = MIN_CHARS) -> bool:
    """Vrai si cette réunion attend encore un nom.

    Fonction pure : c'est elle qui porte la règle « on n'écrase pas un titre
    choisi », et elle se teste sans modèle.
    """
    if meeting is None:
        return False
    if meeting.title != meetings.default_title(meeting.started_at):
        return False
    return sum(len(e.get("text", "")) for e in entries) >= min_chars


def suggest_title(entries: list[dict]) -> str:
    """Titre proposé par le modèle local, ou "" si rien d'exploitable."""
    text = "\n".join(e.get("text", "") for e in entries)
    if not text.strip():
        return ""
    try:
        from benji.llm import mlx_runner, model_cache
        from benji.llm.summarizer import MODEL_ID

        model, tokenizer = model_cache.load(MODEL_ID)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(text)},
        ]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        raw = mlx_runner.generate(model, tokenizer, prompt, 24)
    except Exception as e:
        log.warning("Titre automatique indisponible (%s)", e)
        return ""
    return clean_title(raw)


class MeetingTitler:
    """Nomme la réunion en cours dès qu'elle a de quoi être nommée.

    Un fil de fond, comme `LiveSummarizer` : le modèle met plusieurs secondes à
    répondre et n'a rien à faire sur le thread STT ni sur celui de Qt.
    """

    def __init__(
        self,
        interval_seconds: int = 45,
        min_chars: int = MIN_CHARS,
        on_renamed: Callable[[], None] | None = None,
        suggester: Callable[[list[dict]], str] = suggest_title,
        history: TranscriptionHistory | None = None,
    ):
        self.interval = interval_seconds
        self.min_chars = min_chars
        self.on_renamed = on_renamed
        self._suggest = suggester
        self.history = history or TranscriptionHistory()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Réunions déjà traitées — nommées ou abandonnées après trop d'échecs.
        self._settled: set[str] = set()
        self._attempts: dict[str, int] = {}

    def start(self) -> None:
        if self.interval <= 0:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="MeetingTitler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception as e:
                log.warning("Titre automatique ignoré (%s)", e)

    def tick(self) -> bool:
        """Une passe. Renvoie True si la réunion vient d'être nommée."""
        meeting_id = meetings.current_meeting_id()
        if meeting_id is None or meeting_id in self._settled:
            return False
        store = meetings.store()
        meeting = store.get(meeting_id)
        entries = self.history.get_for_meeting(meeting_id)
        if not needs_title(meeting, entries, self.min_chars):
            return False

        title = self._suggest(entries)
        if not title:
            # Trois échecs et on renonce : un modèle qui répond à côté sur ce
            # transcript continuera, et réessayer coûte une génération complète
            # à chaque tour.
            self._attempts[meeting_id] = self._attempts.get(meeting_id, 0) + 1
            if self._attempts[meeting_id] >= 3:
                self._settled.add(meeting_id)
            return False

        store.rename(meeting_id, title)
        self._settled.add(meeting_id)
        # Le titre est du contenu de réunion : il ne va pas dans le log.
        log.info("Réunion nommée automatiquement")
        if self.on_renamed is not None:
            self.on_renamed()
        return True
