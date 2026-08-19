"""Cache partagé des modèles MLX-LM, indexé par identifiant.

Le correcteur et le résumeur utilisent le même modèle (Qwen2.5-1.5B-4bit) mais
avaient chacun leur cache : activer correction *et* résumé en direct chargeait
deux fois les mêmes poids, soit environ 1 Go de RAM gaspillé sur une machine où
Whisper occupe déjà la place. Un seul cache, une seule copie.

Le verrou est global et non par identifiant : deux chargements simultanés de
modèles différents sont un cas qui n'existe pas ici, et sérialiser évite deux
allocations d'un giga en parallèle.
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict[str, tuple] = {}


def load(model_id: str) -> tuple:
    """Renvoie `(model, tokenizer)` pour *model_id*, en le chargeant au besoin.

    Propage l'exception si le chargement échoue — aux appelants de décider
    entre repli silencieux (correcteur) et remontée (résumeur).
    """
    cached = _cache.get(model_id)
    if cached is not None:
        return cached
    with _lock:
        # Re-test sous verrou : un autre thread a pu charger entre-temps.
        cached = _cache.get(model_id)
        if cached is not None:
            return cached
        from mlx_lm import load as mlx_load

        log.info("Chargement du modèle '%s'...", model_id)
        log.info("(Le premier lancement télécharge le modèle, ~800 Mo)")
        loaded = mlx_load(model_id)
        _cache[model_id] = loaded
        log.info("Modèle '%s' prêt", model_id)
        return loaded


def is_loaded(model_id: str) -> bool:
    return model_id in _cache


def clear() -> None:
    """Vide le cache. Réservé aux tests — libérer les poids en cours de session
    ne sert à rien tant que les deux consommateurs peuvent revenir."""
    with _lock:
        _cache.clear()
