"""Garde-fou global : aucun test ne touche le vrai dossier personnel.

Benji lit et écrit des données réelles sous `~` (historique des réunions,
résumés, identifiants) et sait migrer d'un emplacement à l'autre. Un test qui
laisse fuiter le vrai HOME ne se contente pas de lire à côté : il peut
*déplacer* les transcriptions de l'utilisateur. HOME est donc réécrit vers un
répertoire temporaire pour toute la suite, et l'état de module des réunions est
remis à zéro entre les tests.
"""

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))

    from benji import meetings

    meetings.reset_for_tests()
    yield home
    meetings.reset_for_tests()
