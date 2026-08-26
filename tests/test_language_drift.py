"""La détection de dérive arbitre entre Parakeet et Whisper sur le final.

Ce que ces tests verrouillent : une réunion française normale ne doit **jamais**
déclencher la passe lourde (sinon l'hybride ne sert à rien), et une phrase
réellement partie en anglais doit la déclencher (sinon la garantie de langue est
perdue).
"""

import pytest

from benji.stt.language import drifts_from, marker_counts, tokenize


def test_tokenize_garde_les_elisions():
    assert tokenize("Qu'on ne s'y trompe pas !") == ["qu'on", "ne", "s'y", "trompe", "pas"]


@pytest.mark.parametrize("text", [
    "On va parler de la roadmap produit et des décisions à prendre.",
    "Le kickoff du dashboard est prévu pour la semaine prochaine.",
    "Je pense qu'il faut valider avec le client avant de déployer.",
])
def test_francais_ne_derive_pas(text):
    assert drifts_from(text, "fr") is False


def test_bascule_en_anglais_detectee():
    # Le cas réel qui a motivé le garde-fou (cf. benji/stt/CLAUDE.md).
    text = "the utility devient also the chef d'orchestre"
    assert drifts_from(text, "fr") is True


def test_phrase_anglaise_franche_detectee():
    assert drifts_from("I think that we should ship this by the end of the week", "fr")


def test_segment_trop_court_sabstient():
    """Deux mots ne prouvent rien : s'abstenir coûte moins qu'un faux positif."""
    assert drifts_from("The point", "fr") is False


def test_un_seul_marqueur_ne_suffit_pas():
    """Un anglicisme isolé dans une phrase française n'est pas une dérive."""
    assert drifts_from("On regarde le the dernier point du jour", "fr") is False


def test_langue_auto_ne_derive_jamais():
    """`language=None` : l'utilisateur a demandé la détection auto, il n'y a pas
    de langue de référence à trahir."""
    assert drifts_from("I think that we should ship this by the end", None) is False


def test_langue_non_supportee_ne_derive_pas():
    """Seuls fr et en ont des listes de marqueurs — une autre langue ne doit pas
    déclencher un repli à l'aveugle."""
    assert drifts_from("Wir sollten das bis Ende der Woche liefern", "de") is False


def test_symetrie_anglais_attendu():
    assert drifts_from("Nous allons décider de la suite avec le client", "en") is True
    assert drifts_from("We should decide on the next step with the client", "en") is False


def test_marker_counts_compte_les_deux_langues():
    fr, en = marker_counts("the roadmap de la semaine")
    assert (fr, en) == (2, 1)
