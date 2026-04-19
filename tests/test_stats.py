from benji.stats import SessionStats


def test_initial_snapshot():
    s = SessionStats()
    snap = s.snapshot()
    assert snap["segments"] == 0
    assert snap["latency_p50_ms"] == 0.0


def test_record_and_percentiles():
    s = SessionStats()
    for ms in [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]:
        s.record_segment(audio_seconds=1.0, latency_ms=float(ms))
    snap = s.snapshot()
    assert snap["segments"] == 10
    assert snap["audio_seconds"] == 10.0
    assert 40 <= snap["latency_p50_ms"] <= 60
    assert snap["latency_p95_ms"] >= 90
