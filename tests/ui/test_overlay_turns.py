"""Overlay : un énoncé peut contenir plusieurs tours de parole.

Un segment VAD tient souvent deux locuteurs qui s'enchaînent sans pause
(cf. `benji/stt/diarization.py`). Le transcripteur émet alors un `final_text` par
tour : l'overlay doit les empiler, pas les écraser l'un après l'autre.
"""

from __future__ import annotations

from queue import Queue

from benji.ui.display_bus import DisplayBus
from benji.ui.overlay import SubtitleOverlay


def _overlay(qtbot) -> SubtitleOverlay:
    w = SubtitleOverlay(DisplayBus(Queue()))
    qtbot.addWidget(w)
    return w


def _final(text, speaker=None, **kw):
    d = {"type": "final_text", "text": text}
    if speaker:
        d["speaker"] = speaker
    d.update(kw)
    return d


def test_two_turns_of_one_segment_are_stacked(qtbot):
    w = _overlay(qtbot)
    w._update_word({"type": "segment_start"})
    w._update_word(_final("Je pense que oui", "A"))
    w._update_word(_final("Moi non", "B"))

    shown = w.label.text()
    assert "Je pense que oui" in shown  # la réplique du premier n'est pas effacée
    assert "Moi non" in shown
    assert "<br>" in shown  # une ligne par tour


def test_a_new_utterance_clears_the_previous_turns(qtbot):
    w = _overlay(qtbot)
    w._update_word({"type": "segment_start"})
    w._update_word(_final("Je pense que oui", "A"))
    w._update_word({"type": "segment_start"})
    w._update_word(_final("Autre chose", "A"))

    assert "Je pense que oui" not in w.label.text()


def test_correction_replaces_its_own_turn_only(qtbot):
    w = _overlay(qtbot)
    w._update_word({"type": "segment_start"})
    w._update_word(_final("je pense que oui", "A", seq=1))
    w._update_word(_final("moi non", "B", seq=2))
    w._update_word(_final("Moi, non.", "B", seq=2, corrected=True))

    shown = w.label.text()
    assert "je pense que oui" in shown
    assert "Moi, non." in shown
    assert "moi non" not in shown


def test_late_correction_for_a_gone_segment_is_ignored(qtbot):
    w = _overlay(qtbot)
    w._update_word({"type": "segment_start"})
    w._update_word(_final("premier", "A", seq=1))
    w._update_word({"type": "segment_start"})
    w._update_word(_final("second", "A", seq=2))
    w._update_word(_final("Premier.", "A", seq=1, corrected=True))

    assert w.label.text().endswith("second")
    assert "Premier." not in w.label.text()


def test_markup_in_a_transcription_is_escaped(qtbot):
    w = _overlay(qtbot)
    w._update_word({"type": "segment_start"})
    w._update_word(_final("a <b> & c", "A"))

    assert "&lt;b&gt;" in w.label.text()


def test_drop_clears_every_turn(qtbot):
    w = _overlay(qtbot)
    w._update_word({"type": "segment_start"})
    w._update_word(_final("Je pense que oui", "A"))
    w._update_word({"type": "final_text", "text": "", "drop": True})

    assert w.label.text() == ""
    assert w._final_lines == []
