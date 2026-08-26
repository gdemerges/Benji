"""Analyse d'une combinaison de raccourci global.

Seule cette partie est testable hors session graphique : l'enregistrement passe
par Carbon et n'existe que dans une vraie app. Le reste du module est donc écrit
pour ne jamais lever — un raccourci absent est une gêne, une app qui ne démarre
pas est une panne.
"""

from benji.hotkeys import GlobalHotkeys, parse_shortcut

CMD, SHIFT, ALT, CTRL = 0x0100, 0x0200, 0x0800, 0x1000


def test_combinaison_complete():
    assert parse_shortcut("Ctrl+Alt+Cmd+B") == (11, CTRL | ALT | CMD)


def test_insensible_a_la_casse_et_aux_espaces():
    assert parse_shortcut(" ctrl + SHIFT + r ") == parse_shortcut("Ctrl+Shift+R")


def test_les_synonymes_de_modificateurs():
    assert parse_shortcut("Option+Cmd+M") == parse_shortcut("Alt+Command+M")
    assert parse_shortcut("⌃+⌥+F5") == parse_shortcut("Ctrl+Alt+F5")


def test_une_touche_nue_est_refusee():
    """Réserver une touche sans modificateur la retirerait de toutes les autres
    applications du système."""
    assert parse_shortcut("B") is None
    assert parse_shortcut("F5") is None


def test_combinaisons_illisibles():
    assert parse_shortcut("") is None
    assert parse_shortcut("Ctrl+") is None
    assert parse_shortcut("Ctrl+Nope") is None
    assert parse_shortcut("Ctrl+A+B") is None
    assert parse_shortcut("Ctrl+Shift") is None  # que des modificateurs


def test_un_raccourci_illisible_ne_leve_pas():
    """Le démarrage de l'app ne doit jamais dépendre d'un raccourci."""
    assert GlobalHotkeys().register("Ctrl+Nope", lambda: None) is False


def test_carbon_indisponible_degrade_en_silence(monkeypatch):
    hotkeys = GlobalHotkeys()
    monkeypatch.setattr(hotkeys, "_load", lambda: None)

    assert hotkeys.register("Ctrl+Alt+Cmd+B", lambda: None) is False
    hotkeys.unregister_all()  # ne doit pas lever non plus
