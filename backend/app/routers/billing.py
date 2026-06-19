"""Facturation Stripe.

- POST /v1/billing/checkout : crée une **Checkout Session** Stripe (abonnement Pro)
  et renvoie son URL. Sans clé configurée → repli stub (dev/CI).
- POST /v1/billing/portal : ouvre le **Billing Portal** Stripe pour gérer/résilier
  l'abonnement (nécessite un client Stripe déjà lié).
- POST /v1/billing/webhook : reçoit les events Stripe, **signature HMAC vérifiée**
  (si STRIPE_WEBHOOK_SECRET défini), et met à jour le plan de l'utilisateur.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, Request

from app.auth import User, require_user
from app.config import (
    billing_cancel_url,
    billing_portal_return_url,
    billing_success_url,
    stripe_price_id,
    stripe_secret_key,
    stripe_webhook_secret,
)
from app.db import Database
from app.deps import get_db
from app.errors import ApiError

log = logging.getLogger(__name__)
router = APIRouter()


def _stripe():
    """Charge la lib Stripe à la demande et arme la clé secrète.

    Import paresseux : sans clé configurée, le code (et les tests) ne dépend pas
    de `stripe`. Les tests peuvent monkeypatcher cette fonction.
    """
    import stripe

    stripe.api_key = stripe_secret_key()
    return stripe


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
async def checkout(
    user: User = Depends(require_user),
    db: Database = Depends(get_db),
) -> dict:
    secret, price = stripe_secret_key(), stripe_price_id()
    if not secret or not price:
        # Stripe non configuré → stub (dev/CI). Le client traite l'URL comme
        # n'importe quelle Checkout Session.
        log.warning("STRIPE_SECRET_KEY/STRIPE_PRICE_ID absents — checkout stub (dev only)")
        return {
            "checkout_url": "https://billing.example/checkout/stub",
            "note": "stub — Stripe non configuré",
        }

    row = db.get_user(user.user_id) or {}
    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price, "quantity": 1}],
        # Relie la session à notre utilisateur : le webhook s'en sert pour
        # basculer le plan (cf. webhook ci-dessous).
        "client_reference_id": user.user_id,
        "success_url": billing_success_url(),
        "cancel_url": billing_cancel_url(),
    }
    # Réutilise le client Stripe existant si on le connaît, sinon pré-remplit
    # l'email pour qu'un seul client soit créé côté Stripe.
    if row.get("stripe_customer_id"):
        params["customer"] = row["stripe_customer_id"]
    elif row.get("email"):
        params["customer_email"] = row["email"]

    try:
        session = _stripe().checkout.Session.create(**params)
    except Exception as e:
        log.exception("Stripe: création Checkout Session échouée")
        raise ApiError("upstream_error",
                       "Impossible de créer la session de paiement.", 502) from e
    return {"checkout_url": session.url}


@router.post("/v1/billing/portal")
async def portal(
    user: User = Depends(require_user),
    db: Database = Depends(get_db),
) -> dict:
    """Portail de gestion d'abonnement (changement de carte, résiliation…)."""
    if not stripe_secret_key():
        raise ApiError("bad_request", "Facturation non configurée.", 400)
    row = db.get_user(user.user_id) or {}
    customer = row.get("stripe_customer_id")
    if not customer:
        raise ApiError("bad_request", "Aucun abonnement à gérer.", 400)

    try:
        session = _stripe().billing_portal.Session.create(
            customer=customer,
            return_url=billing_portal_return_url(),
        )
    except Exception as e:
        log.exception("Stripe: création Billing Portal Session échouée")
        raise ApiError("upstream_error",
                       "Impossible d'ouvrir le portail de facturation.", 502) from e
    return {"portal_url": session.url}


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
