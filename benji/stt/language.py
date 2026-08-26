"""Détection de dérive de langue sur le texte d'un segment.

Parakeet fait de la détection automatique sur 25 langues **sans aucun levier
pour la forcer** : au milieu d'une réunion française, un segment difficile
ressort en anglais (« the utility devient also the chef d'orchestre »). Whisper
sait forcer la langue mais coûte ~5× plus cher.

Ce module arbitre entre les deux **après coup** : on décode avec Parakeet, on
regarde le texte produit, et on ne repasse par Whisper que si la langue a
visiblement dérivé. Sur une réunion française propre, la quasi-totalité des
segments évite la passe lourde.

La détection s'appuie sur des **mots-outils**, pas sur du vocabulaire : une
réunion française truffée d'anglicismes métier (« le kickoff du dashboard »)
garde ses « le », « du », « sur » et n'est donc jamais prise pour de l'anglais.
Les mots présents dans les deux langues (« on », « son », « car », « pas »,
« a ») sont volontairement absents des deux listes — ils ne départagent rien.

Module pur : ni modèle, ni I/O. Il se teste sur des chaînes.
"""

from __future__ import annotations

import re

# Mots-outils français sans homographe anglais courant.
FRENCH_MARKERS = frozenset("""
    le les des du de la une un et est sont était étaient être avoir fait
    que qui quoi dont où quand comme mais donc alors ainsi aussi
    je tu il elle nous vous ils elles ne plus moins très bien
    pour dans sur sous avec sans chez vers entre depuis pendant
    ce cet cette ces mon ton notre votre leur leurs mes tes ses nos vos
    au aux celui celle ceux parce puisque toujours jamais déjà encore
    peut peux doit dois veux veut faire dire voir savoir
    oui non merci bonjour voilà ça cela ici
""".split())

# Mots-outils anglais sans homographe français courant.
ENGLISH_MARKERS = frozenset("""
    the this that these those there their they them his her its our your
    and or but so because while when where which who whom whose
    is are was were be been being have has had do does did
    of to in at by for from with without about into over under
    not no yes very also just only even still already again
    would could should will shall can may might must
    what how why thing things something anything everything nothing
    i'm i've don't doesn't didn't it's that's we're you're
""".split())

_WORD_RE = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Mots en minuscules, apostrophes conservées (« don't », « qu'on »)."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


def marker_counts(text: str) -> tuple[int, int]:
    """(mots-outils français, mots-outils anglais) trouvés dans *text*."""
    fr = en = 0
    for word in tokenize(text):
        if word in FRENCH_MARKERS:
            fr += 1
        elif word in ENGLISH_MARKERS:
            en += 1
        elif "'" in word:
            # « qu'on », « l'utilité » : le tokenizer garde l'élision, le
            # marqueur est la particule de gauche.
            head = word.split("'", 1)[0]
            if head in FRENCH_MARKERS:
                fr += 1
    return fr, en


def drifts_from(text: str, expected: str | None, *, min_words: int = 4,
                min_evidence: int = 2) -> bool:
    """Vrai si *text* n'est visiblement pas dans la langue *expected*.

    Conservateur par construction, parce qu'un faux positif coûte une passe
    Whisper inutile mais qu'un faux négatif laisse passer une phrase dans la
    mauvaise langue dans l'historique :

    - moins de `min_words` mots → on s'abstient (« Oui. », « D'accord »
      n'apportent aucune preuve) ;
    - il faut au moins `min_evidence` marqueurs de l'autre langue **et** qu'ils
      soient plus nombreux que ceux de la langue attendue.

    `expected=None` (détection automatique demandée par l'utilisateur) ne dérive
    jamais : il n'y a pas de langue de référence à trahir.
    """
    if not expected:
        return False
    expected = expected.lower()[:2]
    if expected not in ("fr", "en"):
        return False
    words = tokenize(text)
    if len(words) < min_words:
        return False
    fr, en = marker_counts(text)
    if expected == "fr":
        return en >= min_evidence and en > fr
    return fr >= min_evidence and fr > en
