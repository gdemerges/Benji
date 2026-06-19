"""Configuration du backend (variables d'environnement)."""

from __future__ import annotations

import os

# Le client envoie un alias logique (haiku/sonnet/opus) — jamais l'ID Anthropic
# exact. Le mapping vit côté serveur ; la clé API ne quitte jamais le backend.
MODEL_ALIASES: dict[str, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",
}
DEFAULT_MODEL_ALIAS = "haiku"

# Plafond de sortie d'un résumé (tokens). Court par nature.
SUMMARY_MAX_TOKENS = 2048

# Longueur minimale de transcription pour valoir un résumé (caractères).
MIN_TRANSCRIPTION_CHARS = 50


def resolve_model(alias: str | None) -> str:
    """alias logique → ID modèle Anthropic. Inconnu → défaut (haiku)."""
    return MODEL_ALIASES.get((alias or DEFAULT_MODEL_ALIAS).lower(),
                             MODEL_ALIASES[DEFAULT_MODEL_ALIAS])


def anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY")


# --- Auth / JWT ---

ACCESS_TTL_SECONDS = 900            # 15 min
REFRESH_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 jours


def jwt_secret() -> str:
    # ⚠️ Défaut non sûr : définir JWT_SECRET en production.
    return os.environ.get("JWT_SECRET", "dev-insecure-secret-change-me-please-32b+")


def db_path() -> str:
    return os.environ.get("BENJI_DB_PATH", "benji.db")


def stripe_webhook_secret() -> str | None:
    return os.environ.get("STRIPE_WEBHOOK_SECRET")


def stripe_secret_key() -> str | None:
    # Clé secrète Stripe (sk_live_… en prod, sk_test_… en bac à sable).
    return os.environ.get("STRIPE_SECRET_KEY")


def stripe_price_id() -> str | None:
    # ID du Price récurrent (abonnement Pro) — price_… dans le dashboard Stripe.
    return os.environ.get("STRIPE_PRICE_ID")


# URLs de redirection post-paiement / retour du portail. Benji étant une app de
# bureau, on revient par un deep link (surchargeable pour le web/mobile).
def billing_success_url() -> str:
    return os.environ.get("BILLING_SUCCESS_URL", "benji://billing/success")


def billing_cancel_url() -> str:
    return os.environ.get("BILLING_CANCEL_URL", "benji://billing/cancel")


def billing_portal_return_url() -> str:
    return os.environ.get("BILLING_PORTAL_RETURN_URL", "benji://billing/portal")
