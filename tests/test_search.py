"""Recherche plein-texte dans les réunions."""

from benji import search


def _e(text, speaker=None):
    entry = {"text": text}
    if speaker:
        entry["speaker"] = speaker
    return entry


ENTRIES = [
    _e("On revoit le budget du trimestre.", "A"),
    _e("Marie propose de décaler la livraison.", "B"),
    _e("D'accord pour le budget révisé."),
]


def test_recherche_insensible_aux_accents_et_a_la_casse():
    """Un moteur de transcription accentue parfois de travers : chercher
    « revise » doit trouver « révisé »."""
    assert len(search.filter_entries(ENTRIES, "REVISE")) == 1


def test_tous_les_termes_doivent_etre_presents():
    assert len(search.filter_entries(ENTRIES, "budget trimestre")) == 1
    assert search.filter_entries(ENTRIES, "budget licorne") == []


def test_l_ordre_des_termes_est_indifferent():
    assert search.filter_entries(ENTRIES, "trimestre budget") == (
        search.filter_entries(ENTRIES, "budget trimestre")
    )


def test_le_locuteur_est_cherchable():
    """« marie budget » doit trouver ce que Marie a dit du budget."""
    named = [_e("Le budget est validé.", "Marie")]
    assert len(search.filter_entries(named, "marie budget")) == 1


def test_requete_vide_rend_tout():
    assert search.filter_entries(ENTRIES, "") == ENTRIES
    assert search.filter_entries(ENTRIES, "   ") == ENTRIES


def test_l_ordre_d_origine_est_preserve():
    found = search.filter_entries(ENTRIES, "budget")
    assert [e["text"] for e in found] == [
        "On revoit le budget du trimestre.",
        "D'accord pour le budget révisé.",
    ]


def test_une_reunion_est_trouvee_par_son_titre():
    """Les mots du titre n'ont pas à avoir été prononcés dans la même phrase."""
    assert search.meeting_matches("Point produit", [], "point produit") is True


def test_une_reunion_est_trouvee_par_son_contenu():
    assert search.meeting_matches("Réunion du 21/08", ENTRIES, "livraison") is True


def test_une_reunion_sans_rapport_est_ecartee():
    assert search.meeting_matches("Réunion du 21/08", ENTRIES, "licorne") is False


def test_toutes_les_reunions_sans_requete():
    assert search.meeting_matches("N'importe quoi", [], "") is True


def test_entree_sans_texte_ne_leve_pas():
    assert search.filter_entries([{}], "budget") == []
