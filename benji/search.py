"""Recherche plein-texte dans les réunions passées.

Une fenêtre Réunions sans recherche devient un tiroir : à cinquante réunions,
retrouver « ce que le client a dit sur le budget » suppose de se souvenir de la
date. La recherche est donc le geste qui rend l'historique consultable, pas un
raffinement.

Deux règles, choisies pour ce qu'on cherche réellement dans une transcription :

- **Insensible aux accents et à la casse.** On tape « reunion », on veut
  « Réunion » — d'autant qu'un moteur de transcription accentue parfois de
  travers.
- **Tous les mots doivent être présents**, dans n'importe quel ordre et
  n'importe où dans la réunion. « budget client » trouve une réunion où les deux
  ont été dits, même à vingt minutes d'écart : à l'échelle d'une réunion, la
  proximité ne veut rien dire.

Module pur : ni Qt, ni disque. Il se teste sur des listes de dicts.
"""

from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    """Minuscules, accents retirés — la forme sur laquelle on compare."""
    decomposed = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def terms(query: str) -> list[str]:
    """Mots de la requête, normalisés. Requête vide = aucun terme."""
    return [t for t in normalize(query).split() if t]


def entry_matches(entry: dict, needles: list[str]) -> bool:
    """Vrai si l'entrée contient **tous** les termes.

    Le nom du locuteur compte comme du texte cherchable : « marie budget »
    trouve ce que Marie a dit du budget, ce qui est une des façons les plus
    naturelles de fouiller une réunion.
    """
    if not needles:
        return True
    haystack = normalize(f"{entry.get('text', '')} {entry.get('speaker', '')}")
    return all(n in haystack for n in needles)


def filter_entries(entries: list[dict], query: str) -> list[dict]:
    """Entrées correspondant à la requête, dans l'ordre d'origine."""
    needles = terms(query)
    if not needles:
        return list(entries)
    return [e for e in entries if entry_matches(e, needles)]


def meeting_matches(title: str, entries: list[dict], query: str) -> bool:
    """Vrai si une réunion doit rester dans la liste pour cette requête.

    Le **titre** est cherché d'un bloc et le contenu entrée par entrée : taper
    « point produit » doit trouver la réunion qui s'appelle ainsi, même si ces
    deux mots n'ont jamais été prononcés dans la même phrase.
    """
    needles = terms(query)
    if not needles:
        return True
    haystack = normalize(title or "")
    if all(n in haystack for n in needles):
        return True
    return any(entry_matches(e, needles) for e in entries)
