"""Plans d'abonnement → droits et quotas."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    name: str
    cloud_stt: bool
    cloud_summary: bool
    stt_seconds_limit: int | None  # None = illimité


PLANS: dict[str, Plan] = {
    # Gratuit : résumé cloud autorisé (coût négligeable), pas de STT cloud.
    "free": Plan("free", cloud_stt=False, cloud_summary=True, stt_seconds_limit=0),
    # Pro : tout, avec un plafond mensuel d'heures STT (le poste facturable).
    "pro": Plan("pro", cloud_stt=True, cloud_summary=True, stt_seconds_limit=36000),
}

DEFAULT_PLAN = "free"


def get_plan(name: str | None) -> Plan:
    return PLANS.get(name or DEFAULT_PLAN, PLANS[DEFAULT_PLAN])
