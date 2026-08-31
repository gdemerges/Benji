from benji import export


def _entry(ts: str, text: str, speaker: str | None = None) -> dict:
    e = {"timestamp": ts, "text": text}
    if speaker is not None:
        e["speaker"] = speaker
    return e


ENTRIES = [
    _entry("2026-07-12T14:30:01", "Bonjour tout le monde.", "A"),
    _entry("2026-07-12T14:30:05", "Salut à tous.", "B"),
    _entry("2026-07-12T14:30:12", "On commence ?"),
]


def test_distinct_speakers_preserves_order():
    entries = [
        _entry("2026-07-12T14:30:01", "x", "B"),
        _entry("2026-07-12T14:30:02", "y", "A"),
        _entry("2026-07-12T14:30:03", "z", "B"),
        _entry("2026-07-12T14:30:04", "no speaker"),
    ]
    assert export.distinct_speakers(entries) == ["B", "A"]


def test_txt_includes_timestamp_and_speaker():
    out = export.to_txt(ENTRIES)
    lines = out.strip().split("\n")
    assert lines[0] == "[2026-07-12 14:30:01] A : Bonjour tout le monde."
    assert lines[2] == "[2026-07-12 14:30:12] On commence ?"  # pas de locuteur


def test_speaker_renaming_applies():
    out = export.to_txt(ENTRIES, speaker_names={"A": "Alice", "B": "Bob"})
    assert "Alice : Bonjour" in out
    assert "Bob : Salut" in out
    assert "A :" not in out


def test_blank_rename_falls_back_to_label():
    out = export.to_txt(ENTRIES, speaker_names={"A": "   "})
    assert "A : Bonjour" in out


def test_markdown_has_title_and_speaker():
    out = export.to_markdown(ENTRIES, speaker_names={"A": "Alice"})
    assert out.startswith("# Transcription — 2026-07-12")
    assert "**Alice**" in out
    assert "`14:30:01`" in out


def test_srt_structure_and_timing():
    out = export.to_srt(ENTRIES, speaker_names={"A": "Alice"})
    blocks = out.strip().split("\n\n")
    assert len(blocks) == 3
    first = blocks[0].split("\n")
    assert first[0] == "1"
    # segment 1 : 0s -> début du segment 2 (4s plus tard)
    assert first[1] == "00:00:00,000 --> 00:00:04,000"
    assert first[2] == "Alice: Bonjour tout le monde."
    # dernier segment : durée estimée (> 0)
    last = blocks[2].split("\n")
    start, end = last[1].split(" --> ")
    assert start == "00:00:11,000"
    assert end > start


def test_srt_last_segment_uses_estimated_duration():
    single = [_entry("2026-07-12T14:30:00", "Salut.")]
    out = export.to_srt(single)
    line = out.strip().split("\n")[1]
    start, end = line.split(" --> ")
    assert start == "00:00:00,000"
    assert end == "00:00:01,500"  # min 1.5s


def test_render_dispatches_and_rejects_unknown():
    assert export.render(ENTRIES, "txt") == export.to_txt(ENTRIES)
    assert export.render(ENTRIES, "md") == export.to_markdown(ENTRIES)
    assert export.render(ENTRIES, "srt") == export.to_srt(ENTRIES)
    try:
        export.render(ENTRIES, "pdf")
        assert False, "should raise"
    except ValueError:
        pass


def test_empty_entries():
    assert export.to_txt([]) == ""
    assert export.to_srt([]) == ""
    assert "Aucune transcription" in export.to_markdown([])


def test_entries_sorted_and_blank_filtered():
    scrambled = [
        _entry("2026-07-12T14:30:12", "troisième"),
        _entry("2026-07-12T14:30:01", "premier"),
        _entry("2026-07-12T14:30:05", "   "),  # vide → filtré
    ]
    out = export.to_txt(scrambled)
    lines = out.strip().split("\n")
    assert len(lines) == 2
    assert "premier" in lines[0]
    assert "troisième" in lines[1]


# --- moments marqués ---


def _entries_marquables():
    return [
        {"timestamp": "2026-08-31T14:00:00", "text": "Premier point.", "speaker": "A"},
        {"timestamp": "2026-08-31T14:05:00", "text": "Le chiffre important.", "speaker": "B"},
    ]


def test_le_txt_signale_les_lignes_marquees():
    """Un compte rendu exporté sans elles perdrait ce que quelqu'un a désigné."""
    from datetime import datetime

    out = export.to_txt(_entries_marquables(), None, [datetime(2026, 8, 31, 14, 5, 30)])

    lignes = out.strip().splitlines()
    assert not lignes[0].startswith(export.MARK_GLYPH)
    assert lignes[1].startswith(export.MARK_GLYPH)


def test_le_markdown_signale_les_lignes_marquees():
    from datetime import datetime

    out = export.to_markdown(_entries_marquables(), None, [datetime(2026, 8, 31, 14, 5, 30)])

    assert export.MARK_GLYPH in out
    assert out.count(export.MARK_GLYPH) == 1


def test_le_srt_ignore_les_marques():
    """Un sous-titre n'est pas un compte rendu."""
    from datetime import datetime

    out = export.to_srt(_entries_marquables(), None, [datetime(2026, 8, 31, 14, 5, 30)])

    assert export.MARK_GLYPH not in out


def test_sans_marque_le_rendu_est_inchange():
    assert export.to_txt(_entries_marquables()) == export.to_txt(_entries_marquables(), None, [])
