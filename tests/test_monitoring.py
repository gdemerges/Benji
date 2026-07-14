"""Scrubbing Sentry : aucun contenu de réunion, chemin perso ni jeton ne sort."""

from pathlib import Path

from benji.monitoring import _scrub_event, init_sentry


def test_disabled_without_dsn(monkeypatch):
    monkeypatch.delenv("BENJI_SENTRY_DSN", raising=False)
    assert init_sentry() is False


def test_stack_frame_locals_are_stripped():
    # LE vecteur de fuite : une exception dans transcriber.py a le texte de la
    # réunion dans ses variables locales (`full_text`, `corrected`).
    event = {
        "exception": {
            "values": [{
                "value": "boom",
                "stacktrace": {"frames": [{
                    "function": "_run_segment",
                    "vars": {"full_text": "le chiffre d'affaires est de 4 millions"},
                }]},
            }]
        }
    }
    scrubbed = _scrub_event(event)

    frame = scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "vars" not in frame
    assert "chiffre d'affaires" not in str(scrubbed)


def test_tokens_are_redacted():
    event = {
        "exception": {"values": [{
            "value": "401 avec Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abc",
        }]},
        "breadcrumbs": {"values": [{"message": "clé sk-ant-api03-abcdefghijklmnop"}]},
    }
    scrubbed = _scrub_event(event)

    assert "eyJhbGci" not in str(scrubbed)
    assert "sk-ant-api03" not in str(scrubbed)
    assert "[REDACTED]" in scrubbed["exception"]["values"][0]["value"]


def test_home_path_is_anonymized():
    home = str(Path.home())
    event = {"logentry": {"message": f"échec d'écriture dans {home}/Library/Logs/Benji"}}

    scrubbed = _scrub_event(event)

    assert home not in scrubbed["logentry"]["message"]
    assert scrubbed["logentry"]["message"].startswith("échec d'écriture dans ~/")


def test_event_survives_scrubbing():
    # On veut le crash — on ne jette que son contenu sensible.
    event = {"exception": {"values": [{"value": "ValueError: x"}]}}
    assert _scrub_event(event) is not None
