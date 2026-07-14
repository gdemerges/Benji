"""Remontée des crashs Sentry côté backend — opt-in via `SENTRY_DSN`.

Même règle que le client (cf. `benji/monitoring.py`) : le backend voit passer des
transcriptions (proxy STT) et des jetons. Aucun des deux ne doit atterrir dans un
événement Sentry — d'où `max_request_body_size="never"` (sinon le corps des
requêtes `/v1/summary` partirait, transcription comprise) et le scrubbing des
en-têtes d'autorisation.
"""

from __future__ import annotations

import logging
import os
import re

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(
    r"\b(?:Bearer\s+[\w.\-]+|sk-[\w\-]{16,}|eyJ[\w.\-]{20,})", re.IGNORECASE
)

_SENSITIVE_HEADERS = {"authorization", "cookie", "stripe-signature"}


def _scrub_event(event: dict, hint: dict | None = None) -> dict | None:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)  # corps de requête : peut contenir la transcription
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in _SENSITIVE_HEADERS:
                    headers[name] = "[REDACTED]"

    for exc in event.get("exception", {}).get("values", []) or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = _TOKEN_RE.sub("[REDACTED]", exc["value"])
        for frame in exc.get("stacktrace", {}).get("frames", []) or []:
            frame.pop("vars", None)

    return event


def init_sentry() -> bool:
    """Active Sentry si `SENTRY_DSN` est défini. Retourne True si activé."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False

    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN défini mais sentry-sdk absent")
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("BENJI_ENV", "production"),
        include_local_variables=False,
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        before_send=_scrub_event,
    )
    log.info("Sentry actif (backend)")
    return True
