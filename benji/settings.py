"""Préférences utilisateur persistantes.

Réutilise `QSettings("benji", "benji")` — le même magasin natif que
`main_window.py` emploie déjà pour la géométrie de fenêtre — plutôt que
d'introduire un fichier de config concurrent. La règle CLAUDE.md « no config
files » vise la configuration *du repo* (`benji/config.py` reste la source de
vérité des défauts) ; ceci n'est que l'état utilisateur runtime, au même titre
que `~/.cache/benji/credentials.json`.

Au démarrage, `hydrate()` applique les valeurs sauvegardées sur les dataclasses
de config fraîchement instanciées dans `main.py`. Le panneau Préférences écrit
chaque changement immédiatement via `set_value()`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSettings

_ORG = "benji"
_APP = "benji"
_PREFIX = "prefs/"


@dataclass(frozen=True)
class PrefSpec:
    """Lie une clé persistée à un attribut d'une dataclass de config."""

    key: str          # clé logique (préfixée `prefs/` dans QSettings)
    target: str       # "stt" | "ui"
    attr: str         # nom de l'attribut sur la config cible
    kind: type        # int | float | str | bool
    nullable: bool = False  # str seulement : "" persisté ↔ None (ex. langue = auto)
    restart: bool = False   # True = ne prend effet qu'au redémarrage


# Ordre = ordre d'affichage dans le panneau. `restart` documente l'effet.
PREFS: tuple[PrefSpec, ...] = (
    # --- Transcription (redémarrage requis) ---
    PrefSpec("language", "stt", "language", str, nullable=True, restart=True),
    PrefSpec("model_size", "stt", "model_size", str, restart=True),
    PrefSpec("diarization", "stt", "diarization", bool, restart=True),
    PrefSpec("live_summary_interval_s", "stt", "live_summary_interval_s", int, restart=True),
    # --- Affichage (application live) ---
    PrefSpec("font_family", "ui", "font_family", str),
    PrefSpec("font_size", "ui", "font_size", int),
    PrefSpec("bg_opacity", "ui", "bg_opacity", int),
    PrefSpec("display_duration_ms", "ui", "display_duration_ms", int),
)

_BY_KEY = {p.key: p for p in PREFS}


def _coerce(spec: PrefSpec, raw):
    """Convertit une valeur QSettings (souvent str) vers le type Python attendu."""
    if spec.nullable and (raw is None or raw == ""):
        return None
    if spec.kind is bool:
        return raw in (True, 1, "1", "true", "True")
    if spec.kind is int:
        return int(raw)
    if spec.kind is float:
        return float(raw)
    return str(raw)


def _encode(spec: PrefSpec, value):
    """Sérialise une valeur Python pour QSettings (None → "" pour les champs nullable)."""
    if spec.nullable and value is None:
        return ""
    if spec.kind is bool:
        return bool(value)
    return value


class UserSettings:
    """Lecture/écriture des préférences via un `QSettings` injectable."""

    def __init__(self, qsettings: QSettings | None = None):
        self._s = qsettings if qsettings is not None else QSettings(_ORG, _APP)

    def get(self, key: str, default=None):
        spec = _BY_KEY[key]
        raw = self._s.value(_PREFIX + key)
        if raw is None:
            return default
        return _coerce(spec, raw)

    def set_value(self, key: str, value) -> None:
        spec = _BY_KEY[key]
        self._s.setValue(_PREFIX + key, _encode(spec, value))
        self._s.sync()

    def hydrate(self, *, stt=None, ui=None) -> None:
        """Applique les valeurs persistées sur les dataclasses de config fournies.

        Les clés absentes laissent le défaut de `config.py` intact.
        """
        targets = {"stt": stt, "ui": ui}
        for spec in PREFS:
            obj = targets.get(spec.target)
            if obj is None:
                continue
            raw = self._s.value(_PREFIX + spec.key)
            if raw is None:
                continue
            setattr(obj, spec.attr, _coerce(spec, raw))
