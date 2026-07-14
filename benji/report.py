"""Rapport de bug : construction du corps de mail (rendu pur, sans Qt).

Le corps est volontairement composé de faits **anonymes** : version, plateforme,
config du moteur, métriques de session. Jamais de texte transcrit, de chemin
d'historique ni de jeton — le log fichier obéit à la même règle (cf.
`benji/logging_config.py`). Un `mailto:` ne pouvant pas porter de pièce jointe,
les stats voyagent dans le corps et le log est révélé au Finder à côté.
"""

from __future__ import annotations

import platform
import sys
from urllib.parse import quote

from benji import __version__

SUPPORT_EMAIL = "guillaume.demerges@protonmail.com"

# Au-delà, les clients mail (et certains navigateurs) tronquent le mailto:.
_MAX_BODY_CHARS = 1800


def _format_stats(snapshot: dict) -> list[str]:
    lines = [
        f"- Durée de session : {snapshot['session_duration_s'] / 60:.1f} min",
        f"- Segments : {snapshot['segments']} ({snapshot['audio_seconds']:.0f}s d'audio)",
        f"- Latence finale : p50 {snapshot['latency_p50_ms']:.0f} ms · "
        f"p95 {snapshot['latency_p95_ms']:.0f} ms",
        f"- Latence partielle : p50 {snapshot['partial_latency_p50_ms']:.0f} ms · "
        f"p95 {snapshot['partial_latency_p95_ms']:.0f} ms",
    ]
    drops = snapshot.get("drops") or {}
    if drops:
        detail = ", ".join(f"{reason} ×{n}" for reason, n in sorted(drops.items()))
        lines.append(f"- Incidents : {detail}")
    else:
        lines.append("- Incidents : aucun")
    return lines


def build_report_body(
    stats_snapshot: dict | None = None,
    stt_config=None,
    log_path: str | None = None,
) -> str:
    """Corps du mail de rapport. Aucune donnée personnelle, par construction."""
    lines = [
        "Décrivez le problème ici (ce que vous faisiez, ce qui était attendu) :",
        "",
        "",
        "---",
        "Informations techniques (anonymes, jointes automatiquement)",
        "",
        f"- Benji {__version__}",
        f"- macOS {platform.mac_ver()[0] or platform.release()} ({platform.machine()})",
        f"- Python {sys.version.split()[0]}",
    ]

    if stt_config is not None:
        lines += [
            f"- Moteur STT : {stt_config.stt_provider} / modèle {stt_config.model_size}",
            f"- Langue : {stt_config.language} · diarisation : "
            f"{stt_config.diarization_backend if stt_config.diarization else 'off'}",
        ]

    if stats_snapshot is not None:
        lines += ["", "Métriques de session :", *_format_stats(stats_snapshot)]

    if log_path:
        lines += [
            "",
            f"Journal : {log_path}",
            "(le fichier vient d'être révélé dans le Finder — "
            "glissez-le en pièce jointe s'il vous est demandé)",
        ]

    return "\n".join(lines)


def build_mailto_url(
    stats_snapshot: dict | None = None,
    stt_config=None,
    log_path: str | None = None,
) -> str:
    subject = f"Benji {__version__} — signalement"
    body = build_report_body(stats_snapshot, stt_config, log_path)
    if len(body) > _MAX_BODY_CHARS:
        body = body[:_MAX_BODY_CHARS] + "\n…(tronqué)"
    # quote() et non quote_plus() : un « + » dans un mailto: reste un « + »,
    # alors qu'un espace encodé en « + » s'afficherait littéralement.
    return f"mailto:{SUPPORT_EMAIL}?subject={quote(subject)}&body={quote(body)}"
