"""Facturation (fondations).

- POST /v1/billing/checkout : amorce un abonnement (stub — l'intégration Stripe
  réelle, création de Checkout Session via l'API Stripe, reste à brancher).
- POST /v1/billing/webhook : reçoit les events Stripe, **signature HMAC vérifiée**
  (si STRIPE_WEBHOOK_SECRET défini), et met à jour le plan de l'utilisateur.

L'intégration Stripe live (clés, produits, portail) est laissée en TODO ; la
vérification de signature et la bascule de plan sont, elles, réelles et testées.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, Request

from app.auth import User, require_user
from app.config import stripe_webhook_secret
from app.db import Database
from app.deps import get_db
from app.errors import ApiError

log = logging.getLogger(__name__)
router = APIRouter()


def _verify_stripe_signature(payload: bytes, sig_header: str | None, secret: str) -> bool:
    """Vérifie l'en-tête `Stripe-Signature` (schéma t=...,v1=...)."""
    if not sig_header:
        return False
    parts = dict(
        p.split("=", 1) for p in sig_header.split(",") if "=" in p
    )
    timestamp, v1 = parts.get("t"), parts.get("v1")
    if not timestamp or not v1:
        return False
    signed = f"{timestamp}.{payload.decode()}".encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


@router.post("/v1/billing/checkout")
async def checkout(user: User = Depends(require_user)) -> dict:
    # TODO(stripe): créer une vraie Checkout Session via l'API Stripe et
    # renvoyer son URL. Pour l'instant, stub.
    return {
        "checkout_url": "https://billing.example/checkout/stub",
        "note": "stub — intégration Stripe à brancher",
    }


@router.post("/v1/billing/webhook")
async def webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None),
    db: Database = Depends(get_db),
) -> dict:
    payload = await request.body()
    secret = stripe_webhook_secret()
    if secret:
        if not _verify_stripe_signature(payload, stripe_signature, secret):
            raise ApiError("unauthenticated", "Signature Stripe invalide.", 401)
    else:
        log.warning("STRIPE_WEBHOOK_SECRET absent — webhook non vérifié (dev only)")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError as e:
        raise ApiError("bad_request", "Payload JSON invalide.", 400) from e

    etype = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    customer_id = obj.get("customer")

    if etype in ("checkout.session.completed", "customer.subscription.created",
                 "customer.subscription.updated"):
        # Activation / renouvellement → plan pro.
        ref = obj.get("client_reference_id")
        if ref and customer_id:
            db.link_stripe_customer(ref, customer_id)
            db.set_plan(ref, "pro")
        elif customer_id:
            db.set_plan_by_customer(customer_id, "pro")
    elif etype == "customer.subscription.deleted":
        if customer_id:
            db.set_plan_by_customer(customer_id, "free")

    return {"received": True}
