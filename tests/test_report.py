from urllib.parse import parse_qs, unquote, urlparse

from benji import __version__
from benji.config import STTConfig
from benji.report import SUPPORT_EMAIL, build_mailto_url, build_report_body
from benji.stats import SessionStats


def _snapshot() -> dict:
    s = SessionStats()
    s.record_segment(audio_seconds=2.0, latency_ms=120.0)
    s.record_segment(audio_seconds=3.0, latency_ms=340.0)
    s.record_drop("transcribe_queue_full")
    return s.snapshot()


def test_body_carries_diagnostics():
    body = build_report_body(_snapshot(), STTConfig(), log_path="/tmp/benji.log")

    assert __version__ in body
    assert "Segments : 2" in body
    assert "transcribe_queue_full ×1" in body
    assert "modèle" in body  # config du moteur
    assert "/tmp/benji.log" in body


def test_body_reports_no_incident_when_clean():
    s = SessionStats()
    s.record_segment(audio_seconds=1.0, latency_ms=50.0)
    assert "Incidents : aucun" in build_report_body(s.snapshot(), STTConfig())


def test_body_degrades_gracefully_without_stats_or_config():
    body = build_report_body()  # rapport ouvert depuis un état minimal
    assert __version__ in body
    assert "Métriques de session" not in body


def test_body_leaks_no_user_content():
    # Le rapport part par mail : il ne doit contenir que des faits anonymes.
    # Un glossaire utilisateur (noms propres) ne doit pas fuiter non plus.
    cfg = STTConfig(glossary=["Demergès", "ProjetConfidentiel"])
    body = build_report_body(_snapshot(), cfg, log_path="/tmp/benji.log")

    assert "ProjetConfidentiel" not in body
    assert "Demergès" not in body


def test_mailto_url_is_well_formed():
    url = build_mailto_url(_snapshot(), STTConfig())
    parsed = urlparse(url)

    assert parsed.scheme == "mailto"
    assert parsed.path == SUPPORT_EMAIL

    params = parse_qs(parsed.query)
    assert __version__ in unquote(params["subject"][0])
    assert "Segments : 2" in unquote(params["body"][0])


def test_mailto_body_is_truncated():
    # Un corps trop long est tronqué par les clients mail : on tronque nous-mêmes
    # pour que la fin ne soit pas silencieusement perdue.
    huge = {**_snapshot(), "drops": {f"raison_{i}": i for i in range(500)}}
    body = unquote(parse_qs(urlparse(build_mailto_url(huge, STTConfig())).query)["body"][0])

    assert body.endswith("…(tronqué)")
    assert len(body) < 2000
