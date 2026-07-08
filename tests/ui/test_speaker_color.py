"""Speaker → couleur : mapping stable et distinct entre locuteurs."""

from benji.ui.style import speaker_color


def test_same_label_same_color():
    assert speaker_color("A").name() == speaker_color("A").name()


def test_distinct_labels_distinct_colors():
    names = {speaker_color(lbl).name() for lbl in ("A", "B", "C", "D")}
    assert len(names) == 4  # A/B/C/D each get a different color


def test_handles_numeric_overflow_labels():
    # Labels beyond the alphabet (e.g. "S26") must still resolve to a color.
    c = speaker_color("S26")
    assert c.isValid()
