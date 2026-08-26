"""Titre automatique d'une réunion.

Le risque de cette fonction n'est pas de mal nommer : c'est d'écraser ce que
l'utilisateur a choisi, ou de renommer une réunion en boucle pendant qu'elle se
déroule. Les tests portent d'abord là-dessus. Aucun modèle n'est chargé — le
générateur est injecté.
"""

from datetime import datetime

from benji import meetings
from benji.history import TranscriptionHistory
from benji.llm.titler import MeetingTitler, clean_title, needs_title

# --- nettoyage de la sortie du modèle ---

def test_le_preambule_et_les_guillemets_sont_retires():
    assert clean_title('Titre : "Revue budget T3".') == "Revue budget T3"
    assert clean_title("« Point produit »") == "Point produit"


def test_seule_la_premiere_ligne_compte():
    raw = "Revue budget T3\n\nCe titre reflète les sujets abordés."
    assert clean_title(raw) == "Revue budget T3"


def test_un_titre_trop_long_est_tronque_sur_un_mot():
    long = "Réunion de suivi hebdomadaire du projet de migration vers la nouvelle plateforme"
    title = clean_title(long)
    assert len(title) <= 60
    assert not title.endswith(" ")
    assert long.startswith(title)


def test_une_sortie_inutilisable_est_rejetee():
    """Garder l'horodatage vaut mieux qu'un titre absurde."""
    assert clean_title("") == ""
    assert clean_title("Bien") == ""      # un mot seul ne nomme pas une réunion
    assert clean_title("   \n  ") == ""


# --- condition de déclenchement ---

def _meeting(title=None, started=None):
    started = started or datetime(2026, 8, 21, 14, 32)
    return meetings.Meeting(
        id="m1", title=title or meetings.default_title(started), started_at=started
    )


def test_il_faut_assez_de_texte():
    entries = [{"text": "Bonjour, vous m'entendez ?"}]
    assert needs_title(_meeting(), entries) is False


def test_un_titre_par_defaut_et_assez_de_texte_declenche():
    entries = [{"text": "x" * 400}]
    assert needs_title(_meeting(), entries) is True


def test_un_titre_choisi_a_la_main_nest_jamais_ecrase():
    entries = [{"text": "x" * 400}]
    assert needs_title(_meeting(title="Mon titre à moi"), entries) is False


def test_pas_de_reunion_pas_de_titre():
    assert needs_title(None, [{"text": "x" * 400}]) is False


# --- passe complète ---

def _titler(suggester, tmp_path, min_chars=300):
    return MeetingTitler(
        interval_seconds=0,
        min_chars=min_chars,
        suggester=suggester,
        history=TranscriptionHistory(path=tmp_path / "history.jsonl"),
    )


def test_la_reunion_en_cours_est_renommee(tmp_path):
    titler = _titler(lambda entries: "Revue budget T3", tmp_path)
    meeting = meetings.current_meeting()
    titler.history.add("x" * 400, meeting_id=meeting.id)

    assert titler.tick() is True
    assert meetings.store().get(meeting.id).title == "Revue budget T3"


def test_on_ne_renomme_quune_fois(tmp_path):
    calls = []
    titler = _titler(lambda e: calls.append(1) or "Revue budget T3", tmp_path)
    meeting = meetings.current_meeting()
    titler.history.add("x" * 400, meeting_id=meeting.id)

    titler.tick()
    titler.tick()

    assert len(calls) == 1


def test_le_callback_previent_l_interface(tmp_path):
    seen = []
    titler = _titler(lambda e: "Revue budget T3", tmp_path)
    titler.on_renamed = lambda: seen.append(1)
    meeting = meetings.current_meeting()
    titler.history.add("x" * 400, meeting_id=meeting.id)

    titler.tick()

    assert seen == [1]


def test_on_renonce_apres_trois_echecs(tmp_path):
    """Un modèle qui répond à côté sur ce transcript continuera : réessayer
    coûte une génération complète à chaque tour."""
    calls = []
    titler = _titler(lambda e: calls.append(1) or "", tmp_path)
    meeting = meetings.current_meeting()
    titler.history.add("x" * 400, meeting_id=meeting.id)

    for _ in range(6):
        titler.tick()

    assert len(calls) == 3
    assert meetings.store().get(meeting.id).title.startswith("Réunion du")


def test_sans_reunion_ouverte_rien_ne_se_passe(tmp_path):
    """Une réunion n'est ouverte que par la première phrase transcrite : le
    titreur ne doit surtout pas en créer une par curiosité."""
    calls = []
    titler = _titler(lambda e: calls.append(1) or "Titre", tmp_path)

    assert titler.tick() is False
    assert meetings.current_meeting_id() is None
    assert calls == []


def test_un_generateur_qui_leve_ne_casse_rien(tmp_path):
    def _boom(entries):
        raise RuntimeError("modèle absent")

    titler = _titler(_boom, tmp_path)
    meeting = meetings.current_meeting()
    titler.history.add("x" * 400, meeting_id=meeting.id)

    titler._stop.set()
    try:
        titler.tick()
    except RuntimeError:
        pass  # la boucle de fond attrape ; tick() peut propager
    assert meetings.store().get(meeting.id).title.startswith("Réunion du")
