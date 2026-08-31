"""Fil unique d'exécution pour tout ce qui touche à mlx-lm.

**Un stream MLX appartient au thread qui l'a créé.** Ce n'est pas une
préférence de conception, c'est une contrainte de la bibliothèque : un
`mx.stream(s)` ouvert depuis un autre thread lève « There is no Stream(gpu, N)
in current thread », et aucun contournement n'existe côté appelant. Le
`benji/CLAUDE.md` racine porte déjà cette leçon pour Parakeet, chargé sur le
thread principal pour cette exact raison.

`mlx_lm` la rend plus vicieuse encore : son module `generate` crée un
`generation_stream` **à l'import**, une fois pour toutes. Le stream appartient
donc au premier thread qui importe `mlx_lm`, où qu'il soit — et tout autre
consommateur plante. Or Benji en a quatre, chacun sur son fil : le correcteur
(thread STT), le titreur, le résumé en direct, et le `SummaryWorker` de Qt.
Le premier arrivé confisquait le moteur ; les autres échouaient.

D'où ce fil, qui fait deux choses :

1. **Toute** inférence mlx-lm y passe, chargement des poids compris — MLX lie un
   tableau au thread qui l'évalue en premier, des poids chargés ailleurs
   seraient inutilisables ici.
2. Il **s'approprie** le `generation_stream` du module (`_claim_generation_stream`),
   au cas où un autre thread aurait importé `mlx_lm` avant lui. Un stream ne se
   déplace pas d'un fil à l'autre : on le remplace.

Les appelants soumettent une fonction et attendent le résultat — l'exception
éventuelle leur est relancée avec sa trace d'origine.

Sérialiser n'est pas un prix, c'est un gain : trois consommateurs qui
attaqueraient le même modèle de 1,5 Md de paramètres en parallèle sur un GPU
unique se ralentiraient mutuellement.

Le fil est *daemon* et paresseux : sans résumé, correction ni titre, il n'existe
jamais. Rien n'y transite qui doive survivre à la fermeture, donc l'arrêt ne
l'attend pas — une génération en vol est jetée avec le process.
"""

from __future__ import annotations

import logging
import threading
from queue import Queue

log = logging.getLogger(__name__)

_STOP = object()


class _Result:
    """Case de retour à un seul usage, entre le demandeur et le fil."""

    def __init__(self):
        self._ready = threading.Event()
        self._value = None
        self._error: BaseException | None = None

    def set(self, value) -> None:
        self._value = value
        self._ready.set()

    def fail(self, error: BaseException) -> None:
        self._error = error
        self._ready.set()

    def wait(self):
        self._ready.wait()
        if self._error is not None:
            # Relancé tel quel : la trace d'origine est portée par l'objet, donc
            # le journal montre l'échec de génération et non ce réveil-ci.
            raise self._error
        return self._value


_lock = threading.Lock()
_queue: Queue = Queue()
_thread: threading.Thread | None = None


def _claim_generation_stream() -> None:
    """Réattribue le stream de génération de `mlx_lm` au fil courant.

    Faire passer tout le monde par un fil unique ne suffit pas : si un autre
    thread a importé `mlx_lm` avant lui — un import de commodité, une
    dépendance tierce — le `generation_stream` du module lui appartient déjà et
    reste inutilisable ici. On ne peut pas déplacer un stream ; on en crée un
    et on le substitue. Ce fil étant le seul à générer, cette appropriation est
    exacte plutôt qu'opportuniste.

    Un échec est journalisé mais n'interrompt rien : `mlx_lm` peut changer la
    forme de son module, et aucun résumé ne vaut de faire tomber l'appel. En
    WARNING et pas en DEBUG — c'est précisément le silence d'un `except` qui a
    masqué une première version fautive de cette fonction.
    """
    try:
        import sys

        import mlx.core as mx
        import mlx_lm  # noqa: F401 — pour peupler sys.modules

        # `sys.modules` et non `mlx_lm.generate` : le paquet fait
        # `from .generate import generate`, donc l'attribut du même nom est la
        # **fonction**, et lui poser un `generation_stream` ne toucherait pas au
        # module que lit `stream_generate`.
        module = sys.modules["mlx_lm.generate"]
        module.generation_stream = mx.new_stream(mx.default_device())
    except Exception as e:  # noqa: BLE001
        log.warning("Stream de génération mlx-lm non réattribué (%s)", e)


def _loop() -> None:
    claimed = False
    while True:
        job = _queue.get()
        if job is _STOP:
            break
        fn, args, kwargs, result = job
        if not claimed:
            # Au premier travail seulement : importer mlx_lm coûte plusieurs
            # secondes, et un fil créé pour rien ne doit rien payer.
            _claim_generation_stream()
            claimed = True
        try:
            result.set(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001 — relancé chez le demandeur
            result.fail(e)


def _ensure_thread() -> threading.Thread:
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, daemon=True, name="MLXRunner")
            _thread.start()
        return _thread


def run(fn, *args, **kwargs):
    """Exécute *fn* sur le fil MLX et renvoie son résultat (ou relance son erreur).

    Bloque l'appelant le temps de la génération — c'est voulu : les appelants
    sont déjà des fils de fond (correcteur, titreur, `SummaryWorker`), jamais le
    thread Qt.
    """
    if threading.current_thread() is _thread:
        # Appel imbriqué (une génération qui charge les poids au passage) :
        # repasser par la file s'attendrait soi-même indéfiniment.
        return fn(*args, **kwargs)

    _ensure_thread()
    result = _Result()
    _queue.put((fn, args, kwargs, result))
    return result.wait()


def _generate(model, tokenizer, prompt: str, max_tokens: int) -> str:
    """Exécutée *sur* le fil MLX — d'où l'import de `mlx_lm` ici et pas ailleurs."""
    from mlx_lm import generate as mlx_generate

    return mlx_generate(
        model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False
    )


def generate(model, tokenizer, prompt: str, max_tokens: int) -> str:
    """Génération d'un coup, sur le fil MLX. Bloque jusqu'au texte complet."""
    return run(_generate, model, tokenizer, prompt, max_tokens)


def shutdown() -> None:
    """Demande l'arrêt du fil. Ne bloque pas : réservé à l'hygiène des tests."""
    global _thread
    with _lock:
        if _thread is None:
            return
        _queue.put(_STOP)
        _thread = None
