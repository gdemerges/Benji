"""Remontée des crashs via Sentry — opt-in, et scrubbée par construction.

Désactivé tant que `BENJI_SENTRY_DSN` n'est pas défini : sans DSN, `init_sentry()`
ne fait rien et l'app tourne exactement comme avant.

**Confidentialité.** Benji transcrit des réunions : un événement Sentry ne doit
jamais transporter de contenu utilisateur. Trois fuites possibles, toutes fermées
ici — et c'est le point important de ce module, pas l'init :

1. *Variables locales des stack frames.* Sentry les envoie par défaut. Or une
   exception dans `stt/transcriber.py` a `full_text` / `corrected` dans sa portée,
   c'est-à-dire le texte de la réunion. → `include_local_variables=False`.
2. *Breadcrumbs de logging.* Les logs DEBUG (qui contiennent les transcriptions,
   cf. `logging_config.py`) ne doivent pas être capturés. → breadcrumbs à INFO.
3. *Chemins et jetons* dans les messages. → `_scrub_event` en dernier rempart.

Cf. `benji/report.py`, qui applique la même règle au rapport de bug.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from benji import __version__

log = logging.getLogger(__name__)

# Jetons Bearer/JWT et clés d'API qui pourraient traîner dans un message d'erreur.
_TOKEN_RE = re.compile(
    r"\b(?:Bearer\s+[\w.\-]+|sk-[\w\-]{16,}|hf_[\w]{16,}|eyJ[\w.\-]{20,})",
    re.IGNORECASE,
)


def _redact(text: str, home: str) -> str:
    text = _TOKEN_RE.sub("[REDACTED]", text)
    # Le chemin du home contient le nom de l'utilisateur (et celui de l'historique).
    return text.replace(home, "~") if home else text


def _scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    """`before_send` : dernier rempart avant l'envoi réseau.

    Retourne l'événement nettoyé (jamais None : on veut le crash, pas son contenu).
    """
    home = str(Path.home())

    for key in ("logentry", "message"):
        entry = event.get(key)
        if isinstance(entry, dict) and isinstance(entry.get("message"), str):
            entry["message"] = _redact(entry["message"], home)
        elif isinstance(entry, str):
            event[key] = _redact(entry, home)

    for crumb in event.get("breadcrumbs", {}).get("values", []) or []:
        if isinstance(crumb.get("message"), str):
            crumb["message"] = _redact(crumb["message"], home)

    for exc in event.get("exception", {}).get("values", []) or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = _redact(exc["value"], home)
        # Ceinture et bretelles : include_local_variables=False devrait déjà les
        # avoir supprimées, mais une intégration tierce pourrait les réinjecter.
        for frame in exc.get("stacktrace", {}).get("frames", []) or []:
            frame.pop("vars", None)

    return event


def init_sentry() -> bool:
    """Active Sentry si `BENJI_SENTRY_DSN` est défini. Retourne True si activé."""
    dsn = os.environ.get("BENJI_SENTRY_DSN")
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        log.warning("BENJI_SENTRY_DSN défini mais sentry-sdk absent (uv sync --extra monitoring)")
        return False

    sentry_sdk.init(
        dsn=dsn,
        release=f"benji@{__version__}",
        environment=os.environ.get("BENJI_ENV", "production"),
        # Les trois verrous de confidentialité (cf. docstring du module).
        include_local_variables=False,
        send_default_pii=False,
        max_breadcrumbs=30,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        before_send=_scrub_event,
    )
    log.info("Sentry actif (release benji@%s)", __version__)
    return True
