"""Emplacements sur disque des données utilisateur et du cache.

Distinction volontaire :

- **données utilisateur** (`data_dir`) — transcriptions, résumés, identifiants.
  Sur macOS elles vont dans `~/Library/Application Support/Benji`, la convention
  du système. Elles étaient historiquement dans `~/.cache/benji`, un chemin
  Linux qu'un utilitaire de nettoyage peut légitimement purger : un utilisateur
  y perdait ses réunions sans avoir rien fait de mal. `migrate_legacy()` déplace
  l'existant au premier accès.
- **cache** (`cache_dir`) — poids de modèles re-téléchargeables. Reste dans
  `~/.cache/benji` : là, être purgé est sans conséquence.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from benji.config import IS_MACOS

log = logging.getLogger(__name__)

def _legacy_dir() -> Path:
    """Ancien emplacement, résolu à l'appel.

    Surtout pas une constante de module : figée à l'import, elle capturerait le
    HOME du moment et `migrate_legacy` irait déplacer les vraies données de
    l'utilisateur même quand l'appelant (un test) a réécrit HOME.
    """
    return Path.home() / ".cache" / "benji"


def cache_dir() -> Path:
    """Répertoire des artefacts re-téléchargeables (modèles)."""
    path = _legacy_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_dir() -> Path:
    """Répertoire des données utilisateur, créé si besoin."""
    if IS_MACOS:
        path = Path.home() / "Library" / "Application Support" / "Benji"
    else:
        path = Path.home() / ".local" / "share" / "benji"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_path(name: str) -> Path:
    """Chemin d'une donnée utilisateur, après migration de l'ancien emplacement.

    Idempotent : une fois la cible en place, l'ancien chemin n'est plus consulté.
    """
    target = data_dir() / name
    if not target.exists():
        migrate_legacy(name)
    return target


def migrate_legacy(name: str) -> bool:
    """Déplace `~/.cache/benji/<name>` vers le répertoire de données.

    Renvoie True si un déplacement a eu lieu. Toute défaillance est non fatale :
    on repart d'un fichier vide plutôt que d'empêcher l'app de démarrer.
    """
    source = _legacy_dir() / name
    target = data_dir() / name
    if target.exists() or not source.exists():
        return False
    try:
        shutil.move(str(source), str(target))
    except OSError as e:
        log.warning("Migration de %s impossible (%s) — repart à vide", name, e)
        return False
    log.info("Données migrées vers %s", target.parent)
    return True
