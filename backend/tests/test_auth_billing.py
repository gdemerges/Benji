import hashlib
import hmac
import json
import time

import pytest
from app import deps

# --- Auth ---

def test_register_login_refresh_flow(client):
    r = client.post("/v1/auth/register", json={"email": "u@b.c", "password": "pw"})
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["token_type"] == "Bearer"

    # Le jeton d'accès ouvre /me.
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 200

    # Refresh → nouveau jeton d'accès valide.
    r2 = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 200
    new_access = r2.json()["access_token"]
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 200


def test_register_duplicate_email_rejected(client):
    client.post("/v1/auth/register", json={"email": "dup@b.c", "password": "pw"})
    r = client.post("/v1/auth/register", json={"email": "dup@b.c", "password": "pw"})
    assert r.status_code == 400


def test_login_wrong_password(client):
    client.post("/v1/auth/register", json={"email": "x@b.c", "password": "good"})
    r = client.post("/v1/auth/login", json={"email": "x@b.c", "password": "bad"})
    assert r.status_code == 401


def test_bad_token_rejected(client):
    r = client.get("/v1/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


def test_refresh_token_not_accepted_as_access(client):
    tokens = client.post("/v1/auth/register", json={"email": "r@b.c", "password": "pw"}).json()
    # Le refresh_token ne doit pas authentifier /me (mauvais type).
    r = client.get("/v1/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401


def test_refresh_rotation_issues_new_token(client):
    r0 = client.post("/v1/auth/register", json={"email": "rot@b.c", "password": "pw"}).json()
    r1 = client.post("/v1/auth/refresh", json={"refresh_token": r0["refresh_token"]})
    assert r1.status_code == 200
    new = r1.json()["refresh_token"]
    # La rotation renvoie un refresh_token différent de l'ancien.
    assert new != r0["refresh_token"]
    # Le nouveau refresh fonctionne.
    assert client.post("/v1/auth/refresh", json={"refresh_token": new}).status_code == 200


def test_refresh_reuse_revokes_whole_family(client):
    r0 = client.post("/v1/auth/register", json={"email": "reuse@b.c", "password": "pw"}).json()
    # Première rotation : R0 → R1.
    r1 = client.post("/v1/auth/refresh", json={"refresh_token": r0["refresh_token"]}).json()

    # Rejouer R0 (déjà tourné) → 401 et détection de vol.
    replay = client.post("/v1/auth/refresh", json={"refresh_token": r0["refresh_token"]})
    assert replay.status_code == 401

    # La réutilisation coupe toute la famille : R1 (pourtant valide avant) est mort.
    dead = client.post("/v1/auth/refresh", json={"refresh_token": r1["refresh_token"]})
    assert dead.status_code == 401


def test_auth_rate_limited_after_burst(client, monkeypatch):
    from app import ratelimit
    # Petite limite pour un test rapide et déterministe.
    monkeypatch.setattr(ratelimit._login_limiter, "max_hits", 3)
    ratelimit.reset_all_limiters()

    client.post("/v1/auth/register", json={"email": "rl@b.c", "password": "good"})
    # 3 tentatives autorisées (le register ci-dessus a déjà consommé 1 hit),
    # puis la suivante est bloquée en 429.
    codes = [
        client.post("/v1/auth/login", json={"email": "rl@b.c", "password": "bad"}).status_code
        for _ in range(4)
    ]
    assert 429 in codes
    assert codes[-1] == 429


# --- Quota STT ---

def test_quota_exceeded_blocks_transcribe(client, pro_token, monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    monkeypatch.setenv("STT_BACKEND", "fake")
    db = deps.get_db()
    uid = db.get_user_by_email("pro@b.c")["id"]
    db.add_usage(uid, 36000)  # plafond pro atteint

    with client.websocket_connect("/v1/transcribe") as ws:
        ws.send_text(json.dumps({"type": "start", "token": pro_token}))
        err = ws.receive_json()
        assert err["code"] == "quota_exceeded"
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4429


# --- Billing ---

def test_webhook_dev_unverified_upgrades_plan(client, monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    tokens = client.post("/v1/auth/register", json={"email": "buy@b.c", "password": "pw"}).json()
    uid = deps.get_db().get_user_by_email("buy@b.c")["id"]

    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": uid, "customer": "cus_1"}},
    }
    r = client.post("/v1/billing/webhook", json=event)
    assert r.status_code == 200

    me = client.get("/v1/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}).json()
    assert me["plan"] == "pro"
    assert me["entitlements"]["cloud_stt"] is True


def test_webhook_signature_verification(client, monkeypatch):
    secret = "whsec_test"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    payload = json.dumps({"type": "ping", "data": {"object": {}}}).encode()

    # Mauvaise signature → 401.
    bad = client.post("/v1/billing/webhook", content=payload,
                      headers={"Stripe-Signature": "t=1,v1=deadbeef"})
    assert bad.status_code == 401

    # Bonne signature → 200.
    t = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    good = client.post("/v1/billing/webhook", content=payload,
                       headers={"Stripe-Signature": f"t={t},v1={sig}"})
    assert good.status_code == 200


def test_checkout_stub_requires_auth(client, auth, monkeypatch):
    # Sans clé Stripe → repli stub.
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    assert client.post("/v1/billing/checkout").status_code == 401
    r = client.post("/v1/billing/checkout", headers=auth)
    assert r.status_code == 200
    assert "checkout_url" in r.json()


class _FakeSession:
    """Mime `stripe.checkout.Session` / `stripe.billing_portal.Session`."""

    captured: dict = {}

    @classmethod
    def create(cls, **params):
        cls.captured = params
        return type("S", (), {"url": "https://stripe.test/session/xyz"})()


def _fake_stripe():
    return type(
        "stripe",
        (),
        {
            "checkout": type("c", (), {"Session": _FakeSession}),
            "billing_portal": type("b", (), {"Session": _FakeSession}),
        },
    )


def test_checkout_live_creates_session(client, auth, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_pro")
    from app.routers import billing
    monkeypatch.setattr(billing, "_stripe", _fake_stripe)

    uid = deps.get_db().get_user_by_email("free@b.c")["id"]
    r = client.post("/v1/billing/checkout", headers=auth)
    assert r.status_code == 200
    assert r.json()["checkout_url"] == "https://stripe.test/session/xyz"
    # La session relie bien notre utilisateur (pour le webhook) et le prix Pro.
    sent = _FakeSession.captured
    assert sent["mode"] == "subscription"
    assert sent["client_reference_id"] == uid
    assert sent["customer_email"] == "free@b.c"
    assert sent["line_items"] == [{"price": "price_pro", "quantity": 1}]


def test_checkout_live_reuses_existing_customer(client, auth, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_pro")
    from app.routers import billing
    monkeypatch.setattr(billing, "_stripe", _fake_stripe)

    db = deps.get_db()
    uid = db.get_user_by_email("free@b.c")["id"]
    db.link_stripe_customer(uid, "cus_existing")

    client.post("/v1/billing/checkout", headers=auth)
    sent = _FakeSession.captured
    assert sent["customer"] == "cus_existing"
    assert "customer_email" not in sent


def test_portal_requires_linked_customer(client, auth, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    from app.routers import billing
    monkeypatch.setattr(billing, "_stripe", _fake_stripe)

    # Pas encore de client Stripe → 400.
    assert client.post("/v1/billing/portal", headers=auth).status_code == 400

    db = deps.get_db()
    db.link_stripe_customer(db.get_user_by_email("free@b.c")["id"], "cus_42")
    r = client.post("/v1/billing/portal", headers=auth)
    assert r.status_code == 200
    assert r.json()["portal_url"] == "https://stripe.test/session/xyz"
    assert _FakeSession.captured["customer"] == "cus_42"
