"""LiveTab redesign : état vide, regroupement par locuteur, corrections."""

from __future__ import annotations

from benji.ui.live_tab import LiveTab


def _items(tab: LiveTab):
    """ChatItems présents dans la colonne (sans le stretch final)."""
    out = []
    for i in range(tab.content_layout.count() - 1):
        w = tab.content_layout.itemAt(i).widget()
        if w is not None:
            out.append(w)
    return out


def _final(text, speaker=None, seq=None, **kw):
    d = {"type": "final_text", "text": text, "speaker": speaker, "seq": seq}
    d.update(kw)
    return d


def test_empty_state_then_first_final(qtbot):
    tab = LiveTab()
    qtbot.addWidget(tab)
    tab.show()
    assert tab.empty.isVisible()
    assert not tab.scroll.isVisible()

    tab.on_event(_final("Bonjour.", "A", 1))
    assert not tab.empty.isVisible()
    assert tab.scroll.isVisible()
    assert len(_items(tab)) == 1


def test_grouping_same_speaker_hides_header(qtbot):
    tab = LiveTab()
    qtbot.addWidget(tab)
    tab.on_event(_final("Première phrase.", "A", 1))
    tab.on_event(_final("Deuxième phrase.", "A", 2))
    tab.on_event(_final("Réponse.", "B", 3))
    items = _items(tab)
    assert items[0].speaker_label is not None  # nouveau groupe : en-tête
    assert items[1].speaker_label is None      # même locuteur : pas d'en-tête
    assert items[2].speaker_label is not None  # locuteur différent : en-tête


def test_timestamp_shown_once_per_minute(qtbot):
    tab = LiveTab()
    qtbot.addWidget(tab)
    tab.on_event(_final("Un.", "A", 1))
    tab.on_event(_final("Deux.", "B", 2))  # nouveau groupe, même minute
    items = _items(tab)
    assert items[0].ts_label.text() != ""
    assert items[1].ts_label.text() == ""


def test_correction_replaces_line_without_duplicate(qtbot):
    tab = LiveTab()
    qtbot.addWidget(tab)
    tab.on_event(_final("Texte brut avant correction.", "A", 7))
    tab.on_event(_final("Texte corrigé.", "A", 7, corrected=True))
    items = _items(tab)
    assert len(items) == 1
    assert items[0].text_label.text() == "Texte corrigé."


def test_stale_correction_is_ignored(qtbot):
    tab = LiveTab()
    qtbot.addWidget(tab)
    tab.on_event(_final("Phrase affichée.", "A", 1))
    tab.on_event(_final("Correction orpheline.", "A", 999, corrected=True))
    items = _items(tab)
    assert len(items) == 1
    assert items[0].text_label.text() == "Phrase affichée."


def test_vad_animates_empty_state_wave(qtbot):
    tab = LiveTab()
    qtbot.addWidget(tab)
    tab.on_event({"type": "vad_status", "speaking": True})
    assert tab.empty.wave._active
    tab.on_event({"type": "vad_status", "speaking": False})
    assert not tab.empty.wave._active


def test_partial_line_shows_and_clears(qtbot):
    tab = LiveTab()
    qtbot.addWidget(tab)
    tab.show()
    tab.on_event({"type": "segment_start"})
    tab.on_event({"type": "word", "text": "bonjour"})
    tab.on_event({"type": "word", "text": "monde"})
    assert tab.partial.isVisible()
    assert "bonjour monde" in tab.partial.text_label.text()
    assert tab.partial.wave._active
    tab.on_event(_final("Bonjour monde.", "A", 1))
    assert not tab.partial.isVisible()
