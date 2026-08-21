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


def test_variante_claire_pour_l_overlay():
    """L'overlay est sur fond noir quel que soit le thème : teintes claires.

    Sans ça, un Mac en thème clair peignait les locuteurs dans la famille sombre,
    illisible sur le fond noir de l'overlay.
    """
    on_dark = speaker_color("A", on_dark=True)
    on_light = speaker_color("A", on_dark=False)

    assert on_dark.name() != on_light.name()
    assert on_dark.lightness() > on_light.lightness()
