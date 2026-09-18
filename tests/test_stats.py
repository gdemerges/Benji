from benji.stats import SessionStats, load_last_session


def test_initial_snapshot():
    s = SessionStats()
    snap = s.snapshot()
    assert snap["segments"] == 0
    assert snap["latency_p50_ms"] == 0.0


def test_p95_reaches_the_worst_latency():
    # Rang le plus proche : sur 5 échantillons, le p95 doit être le pire (900),
    # pas l'avant-dernier — sinon les pics de latence passent sous le radar.
    s = SessionStats()
    for ms in [110, 180, 240, 320, 900]:
        s.record_segment(audio_seconds=1.0, latency_ms=float(ms))
    assert s.snapshot()["latency_p95_ms"] == 900.0


def test_record_and_percentiles():
    s = SessionStats()
    for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        s.record_segment(audio_seconds=1.0, latency_ms=float(ms))
    snap = s.snapshot()
    assert snap["segments"] == 10
    assert snap["audio_seconds"] == 10.0
    assert 40 <= snap["latency_p50_ms"] <= 60
    assert snap["latency_p95_ms"] >= 90


def test_save_survives_the_process():
    """Sans persistance, une session qui se termine mal ne laisse aucune trace
    passé le process — le prochain rapport de bug ne parlerait que d'une
    session vierge qui vient de démarrer."""
    assert load_last_session() is None

    s = SessionStats()
    s.record_segment(audio_seconds=2.0, latency_ms=150.0)
    s.record_drop("stt_thread_restart")
    s.save()

    last = load_last_session()
    assert last is not None
    assert last["segments"] == 1
    assert last["drops"] == {"stt_thread_restart": 1}


def test_save_keeps_only_the_bounded_history():
    """Un journal de diagnostic, pas une archive : borné comme la rotation des
    logs (2 Mo × 3), jamais une croissance sans fin."""
    from benji.stats import _MAX_HISTORY

    for i in range(_MAX_HISTORY + 5):
        s = SessionStats()
        s.record_segment(audio_seconds=1.0, latency_ms=float(i))
        s.save()

    last = load_last_session()
    assert last["latency_p50_ms"] == float(_MAX_HISTORY + 4)

    from benji.logging_config import log_dir
    from benji.stats import _HISTORY_NAME

    lines = (log_dir() / _HISTORY_NAME).read_text(encoding="utf-8").splitlines()
    assert len(lines) == _MAX_HISTORY
