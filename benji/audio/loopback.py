"""Détection du périphérique de boucle qui porte l'audio système.

macOS ne laisse aucune API publique capturer la sortie audio depuis un simple
`InputStream` : il faut un pilote virtuel (BlackHole, Loopback, …) que
l'utilisateur route en sortie. Une fois installé, ce pilote apparaît comme un
**périphérique d'entrée** ordinaire — donc `sounddevice` suffit, sans code natif.

Ce module ne fait que du choix : il reçoit une liste de périphériques (des dicts
au format `sd.query_devices()`) et désigne le meilleur candidat. Aucune
dépendance à sounddevice ici, ce qui le rend testable sans matériel.
"""

from __future__ import annotations

from dataclasses import dataclass

# Motifs de noms, du plus au moins fiable. Le score sert à départager quand
# plusieurs pilotes virtuels cohabitent (cas courant : BlackHole installé à côté
# du périphérique audio d'un client de visio).
_KNOWN_LOOPBACKS: tuple[tuple[str, int], ...] = (
    ("blackhole", 100),        # le standard de fait, gratuit et open source
    ("loopback audio", 90),    # Rogue Amoeba Loopback
    ("existential audio", 90), # éditeur de BlackHole (variantes de nommage)
    ("soundflower", 70),       # historique, non maintenu
    ("vb-cable", 70),
    ("vb-audio", 70),
    ("multi-output", 60),      # agrégat créé à la main dans Audio MIDI Setup
    ("aggregate", 60),
    ("ishowu", 50),
    ("audio hijack", 50),
)

# Périphériques virtuels appartenant à une app tierce : ils *peuvent* servir de
# boucle, mais ne captent que cette app et disparaissent quand elle se ferme.
# Proposés en dernier recours, jamais choisis automatiquement.
_APP_OWNED: tuple[str, ...] = (
    "microsoft teams audio",
    "zoomaudiodevice",
    "eshareaudio",
    "krisp",
)


@dataclass(frozen=True)
class LoopbackDevice:
    """Un candidat pour la capture de l'audio système."""

    name: str
    channels: int
    score: int
    app_owned: bool = False

    @property
    def is_reliable(self) -> bool:
        """True si le périphérique est un vrai pilote de boucle système."""
        return not self.app_owned


def _score(name: str) -> tuple[int, bool] | None:
    """Renvoie (score, app_owned) si *name* ressemble à une boucle, sinon None."""
    lowered = name.lower()
    for pattern in _APP_OWNED:
        if pattern in lowered:
            return 10, True
    for pattern, score in _KNOWN_LOOPBACKS:
        if pattern in lowered:
            return score, False
    return None


def find_loopback_devices(devices: list[dict]) -> list[LoopbackDevice]:
    """Classe les périphériques d'entrée qui ressemblent à une boucle système.

    *devices* suit le format `sounddevice.query_devices()` : des dicts avec au
    moins `name` et `max_input_channels`. Le meilleur candidat vient en premier.
    """
    found: list[LoopbackDevice] = []
    for dev in devices:
        channels = dev.get("max_input_channels", 0)
        if channels <= 0:
            continue  # sortie pure : inutilisable en capture
        name = dev.get("name", "")
        scored = _score(name)
        if scored is None:
            continue
        score, app_owned = scored
        found.append(LoopbackDevice(name=name, channels=channels, score=score, app_owned=app_owned))
    # Tri stable : score décroissant, puis nom, pour un résultat déterministe.
    found.sort(key=lambda d: (-d.score, d.name))
    return found


def select_loopback(devices: list[dict], preferred: str | None = None) -> LoopbackDevice | None:
    """Choisit le périphérique de boucle à utiliser.

    Si *preferred* est renseigné (sous-chaîne du nom, tel que persisté dans les
    préférences), il gagne — même s'il appartient à une app : c'est un choix
    explicite de l'utilisateur. Sinon on prend le meilleur candidat *fiable* ;
    un périphérique appartenant à une app n'est jamais sélectionné tout seul,
    parce qu'il ne capterait qu'une application.
    """
    candidates = find_loopback_devices(devices)
    if preferred:
        wanted = preferred.lower()
        for dev in candidates:
            if wanted in dev.name.lower():
                return dev
        return None  # le choix explicite a disparu : ne pas retomber en silence
    reliable = [d for d in candidates if d.is_reliable]
    return reliable[0] if reliable else None
