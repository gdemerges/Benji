"""Registre des réunions : cycle de vie, persistance, robustesse du fichier."""

import json
import os
import stat
from datetime import datetime, timedelta

import pytest

from benji import meetings
from benji.meetings import Meeting, MeetingStore


@pytest.fixture
def store(tmp_path):
    return MeetingStore(path=tmp_path / "meetings.json")


def test_start_ouvre_une_reunion_titree(store):
    meeting = store.start(now=datetime(2026, 8, 21, 14, 30))
    assert meeting.title == "Réunion du 21/08 à 14:30"
    assert meeting.ended_at is None
    assert [m.id for m in store.list()] == [meeting.id]


def test_start_clot_la_precedente(store):
    first = store.start(now=datetime(2026, 8, 21, 9, 0))
    store.start(now=datetime(2026, 8, 21, 10, 0))

    reloaded = store.get(first.id)
    assert reloaded.ended_at == datetime(2026, 8, 21, 10, 0)


def test_list_trie_du_plus_recent_au_plus_ancien(store):
    old = store.start(now=datetime(2026, 8, 20, 9, 0))
    recent = store.start(now=datetime(2026, 8, 21, 9, 0))
    assert [m.id for m in store.list()] == [recent.id, old.id]


def test_rename_et_delete(store):
    meeting = store.start()
    store.rename(meeting.id, "  Point produit  ")
    assert store.get(meeting.id).title == "Point produit"

    # Un titre vide ne doit pas effacer le nom existant.
    store.rename(meeting.id, "   ")
    assert store.get(meeting.id).title == "Point produit"

    store.delete(meeting.id)
    assert store.get(meeting.id) is None


def test_fichier_ecrit_en_0600(store):
    store.start()
    assert stat.S_IMODE(os.stat(store.path).st_mode) == 0o600


def test_fichier_corrompu_ne_fait_pas_perdre_l_app(store):
    store.path.write_text("{pas du json", encoding="utf-8")
    assert store.list() == []
    meeting = store.start()  # on repart proprement
    assert store.get(meeting.id) is not None


def test_entree_invalide_ignoree_sans_perdre_les_autres(store):
    valid = store.start(now=datetime(2026, 8, 21, 9, 0))
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw.append({"id": "cassée"})  # pas de started_at
    store.path.write_text(json.dumps(raw), encoding="utf-8")

    assert [m.id for m in store.list()] == [valid.id]


def test_meeting_roundtrip():
    started = datetime(2026, 8, 21, 9, 0)
    meeting = Meeting(id="x", title="T", started_at=started, ended_at=started + timedelta(hours=1))
    assert Meeting.from_dict(meeting.to_dict()) == meeting


# --- état de module (réunion courante) ---


def test_current_meeting_id_ne_cree_rien():
    """Un chemin de lecture ne doit jamais ouvrir une réunion vide."""
    assert meetings.current_meeting_id() is None
    assert meetings.store().list() == []


def test_current_meeting_est_stable_entre_appels():
    first = meetings.current_meeting()
    assert meetings.current_meeting().id == first.id
    assert meetings.current_meeting_id() == first.id


def test_start_meeting_clot_la_courante():
    first = meetings.current_meeting()
    second = meetings.start_meeting("Rétro")

    assert second.id != first.id
    assert second.title == "Rétro"
    assert meetings.store().get(first.id).ended_at is not None


def test_end_current_meeting_horodate_la_fin():
    meeting = meetings.current_meeting()
    meetings.end_current_meeting()

    assert meetings.store().get(meeting.id).ended_at is not None
    assert meetings.current_meeting_id() is None
