"""Backend Parakeet : regroupement des sous-mots et sélection du moteur.

Parakeet rend des morceaux de mots (`" De"`, `" c"`, `"ô"`, `"té"`) ; tout le
reste de Benji — découpage incrémental, overlay, export SRT — raisonne en mots
horodatés. Le regroupement est donc la pièce à ne pas rater : elle est pure et
testée sans charger le moindre modèle.
"""

from dataclasses import dataclass

import pytest

import benji.stt.backend as backend_mod
from benji.stt.backend import build_backend, group_tokens_into_words, words_from_result


@dataclass
class Tok:
    text: str
    start: float | None = None
    end: float | None = None


def test_les_sous_mots_sont_recolles():
    tokens = [Tok(" De", 0.0, 0.16), Tok(" c", 0.32, 0.4), Tok("ô", 0.4, 0.48),
              Tok("té", 0.48, 0.56)]

    assert [w["text"] for w in group_tokens_into_words(tokens)] == ["De", "côté"]


def test_le_mot_herite_du_debut_du_premier_et_de_la_fin_du_dernier():
    tokens = [Tok(" bu", 0.8, 0.96), Tok("ild", 0.96, 1.12)]

    word = group_tokens_into_words(tokens)[0]

    assert word == {"text": "build", "start": 0.8, "end": 1.12}


def test_la_ponctuation_colle_au_mot_precedent():
    tokens = [Tok(" démarre", 0.2, 0.6), Tok(",", 0.6, 0.62), Tok(" on", 0.7, 0.8)]

    assert [w["text"] for w in group_tokens_into_words(tokens)] == ["démarre,", "on"]


def test_un_premier_token_sans_espace_ouvre_quand_meme_un_mot():
    """Le tout premier morceau d'un tampon n'est pas toujours préfixé d'une espace."""
    assert [w["text"] for w in group_tokens_into_words([Tok("Bon", 0.0, 0.3)])] == ["Bon"]


def test_les_tokens_vides_sont_ignores():
    tokens = [Tok(" un", 0.0, 0.2), Tok("  ", 0.2, 0.21), Tok(" deux", 0.3, 0.5)]

    assert [w["text"] for w in group_tokens_into_words(tokens)] == ["un", "deux"]


def test_timestamps_absents_tolérés():
    """Un mot sans borne doit sortir avec None, jamais lever."""
    words = group_tokens_into_words([Tok(" mot"), Tok("s")])

    assert words == [{"text": "mots", "start": None, "end": None}]


def test_liste_vide():
    assert group_tokens_into_words([]) == []


@dataclass
class Sentence:
    tokens: list


@dataclass
class Result:
    sentences: list


def test_deux_phrases_ne_se_recollent_pas():
    """Le premier morceau d'une phrase n'a pas toujours l'espace de tête.

    Sur les tokens aplatis, la fin d'une phrase se recollait au début de la
    suivante : « Apple.Ça » au lieu de « Apple. » puis « Ça ».
    """
    result = Result([
        Sentence([Tok(" Apple", 1.0, 1.4), Tok(".", 1.4, 1.42)]),
        Sentence([Tok("Ça", 1.6, 1.8), Tok(" prend", 1.8, 2.0)]),
    ])

    assert [w["text"] for w in words_from_result(result)] == ["Apple.", "Ça", "prend"]


def test_resultat_sans_phrase():
    assert words_from_result(Result([])) == []
    assert words_from_result(object()) == []


# --- sélection du moteur ---


def test_parakeet_absent_retombe_sur_whisper(monkeypatch):
    """Un moteur indisponible ne doit jamais empêcher de transcrire."""
    def _boom(model_id):
        raise ImportError("parakeet-mlx not installed")

    monkeypatch.setattr(backend_mod, "ParakeetBackend", _boom)
    built = []

    def _whisper(size, default_beam_size=5):
        built.append(size)
        return type("B", (), {"name": "mlx"})()

    monkeypatch.setattr(backend_mod, "MLXWhisperBackend", _whisper)

    backend = build_backend("medium", 5, 4, engine="parakeet")

    assert backend.name == "mlx"
    assert built == ["medium"]


def test_moteur_whisper_par_defaut(monkeypatch):
    monkeypatch.setattr(
        backend_mod, "ParakeetBackend",
        lambda model_id: pytest.fail("Parakeet ne doit pas être construit par défaut"),
    )
    monkeypatch.setattr(
        backend_mod, "MLXWhisperBackend",
        lambda size, default_beam_size=5: type("B", (), {"name": "mlx"})(),
    )

    assert build_backend("medium", 5, 4).name == "mlx"


def test_le_moteur_choisi_recoit_ses_poids(monkeypatch):
    seen = {}

    def _fake(model_id):
        seen["id"] = model_id
        return type("B", (), {"name": "parakeet"})()

    monkeypatch.setattr(backend_mod, "ParakeetBackend", _fake)

    backend = build_backend("medium", 5, 4, engine="parakeet",
                            parakeet_model="mlx-community/parakeet-tdt-0.6b-v3")

    assert backend.name == "parakeet"
    assert seen["id"] == "mlx-community/parakeet-tdt-0.6b-v3"


# --- le moteur par défaut ---


def test_parakeet_est_le_moteur_par_defaut():
    """Le défaut doit être Parakeet : c'est le seul qui tienne le temps réel.

    Verrouillé ici parce qu'un retour discret à Whisper multiplierait par cinq la
    latence de chaque passe sans que rien ne le signale.
    """
    from benji.config import STTConfig

    assert STTConfig().stt_provider == "parakeet"


def test_le_moteur_par_defaut_est_une_dependance_dure():
    """Le moteur par défaut ne peut pas être un extra optionnel.

    Sinon un `uv sync` nu retombe silencieusement sur Whisper, et l'app tourne
    cinq fois plus lentement que prévu sans que personne le voie.
    """
    import tomllib
    from pathlib import Path

    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    deps = " ".join(pyproject["project"]["dependencies"])

    assert "parakeet-mlx" in deps
    assert "parakeet" not in pyproject["project"].get("optional-dependencies", {})


# --- liaison au thread MLX ---


def test_les_poids_sont_materialises_a_la_construction(monkeypatch):
    """MLX lie les tableaux au stream du thread qui les évalue en premier.

    Sans `mx.eval()` au chargement, la liaison n'a lieu qu'au premier décodage
    réel : toute inférence lancée depuis le thread STT lève alors « There is no
    Stream(gpu, N) in current thread ». On ne peut pas compter sur `warmup()`,
    qui préchauffe sur du silence — Parakeet n'en décode aucun token, donc le
    décodeur ne tourne jamais et rien n'est lié.
    """
    import mlx.core as mx
    import parakeet_mlx

    from benji.stt.backend import ParakeetBackend

    params = {"encoder": "poids"}

    class _FakeModel:
        preprocessor_config = object()

        def parameters(self):
            return params

    evaluated = []
    monkeypatch.setattr(parakeet_mlx, "from_pretrained", lambda model_id: _FakeModel())
    monkeypatch.setattr(mx, "eval", lambda *args: evaluated.append(args))

    ParakeetBackend("mlx-community/parakeet-tdt-0.6b-v3")

    assert evaluated == [(params,)], "les poids doivent être matérialisés au chargement"
