"""Scrubbing Sentry backend : ni corps de requête (transcription) ni jeton."""

from app.monitoring import _scrub_event, init_sentry


def test_disabled_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_request_body_is_dropped():
    # Le corps de /v1/summary contient la transcription complète de l'utilisateur.
    event = {"request": {
        "url": "https://api/v1/summary",
        "data": {"transcript": "le chiffre d'affaires est de 4 millions"},
    }}
    scrubbed = _scrub_event(event)

    assert "data" not in scrubbed["request"]
    assert "chiffre d'affaires" not in str(scrubbed)


def test_sensitive_headers_are_redacted():
    event = {"request": {"headers": {
        "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.abc",
        "Stripe-Signature": "t=1,v1=deadbeef",
        "User-Agent": "Benji/0.1.0",
    }}}
    scrubbed = _scrub_event(event)

    headers = scrubbed["request"]["headers"]
    assert headers["Authorization"] == "[REDACTED]"
    assert headers["Stripe-Signature"] == "[REDACTED]"
    assert headers["User-Agent"] == "Benji/0.1.0"  # le non-sensible est conservé


def test_stack_frame_locals_are_stripped():
    event = {"exception": {"values": [{
        "value": "boom",
        "stacktrace": {"frames": [{"vars": {"password": "hunter2"}}]},
    }]}}
    scrubbed = _scrub_event(event)

    assert "vars" not in scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "hunter2" not in str(scrubbed)
