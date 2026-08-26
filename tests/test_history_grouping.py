"""`group_by_meeting` : une seule lecture pour toute la fenêtre Réunions."""

from benji import meetings
from benji.history import TranscriptionHistory


def test_les_entrees_sont_indexees_par_reunion(tmp_path):
    history = TranscriptionHistory(path=tmp_path / "history.jsonl")
    history.add("un", meeting_id="m1")
    history.add("deux", meeting_id="m2")
    history.add("trois", meeting_id="m1")

    grouped = history.group_by_meeting()

    assert [e["text"] for e in grouped["m1"]] == ["un", "trois"]
    assert [e["text"] for e in grouped["m2"]] == ["deux"]


def test_les_entrees_heritees_tombent_sous_legacy(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text('{"timestamp": "2026-01-01T10:00:00", "text": "ancien"}\n', encoding="utf-8")
    history = TranscriptionHistory(path=path)

    grouped = history.group_by_meeting()

    assert [e["text"] for e in grouped[meetings.LEGACY_ID]] == ["ancien"]


def test_fichier_absent(tmp_path):
    assert TranscriptionHistory(path=tmp_path / "rien.jsonl").group_by_meeting() == {}


def test_une_seule_lecture_du_fichier(tmp_path, monkeypatch):
    """Le point de la méthode : compter les échanges réunion par réunion
    relisait le fichier autant de fois qu'il y a de réunions."""
    history = TranscriptionHistory(path=tmp_path / "history.jsonl")
    for i in range(5):
        history.add(f"phrase {i}", meeting_id=f"m{i}")

    reads = []
    original = TranscriptionHistory._iter_entries

    def _counting(self):
        reads.append(1)
        yield from original(self)

    monkeypatch.setattr(TranscriptionHistory, "_iter_entries", _counting)
    history.group_by_meeting()

    assert len(reads) == 1
