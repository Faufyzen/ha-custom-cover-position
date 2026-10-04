"""Calculs d'un groupe de volets, sans Home Assistant (donc testables seuls).

Un groupe ne calcule aucune position lui-même : il résume ce que ses volets annoncent
(position moyenne, état) et réunit leurs positions prédéfinies par nom.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def cle_nom(nom: str) -> str:
    """Clé de comparaison d'un nom de position : sans casse, sans accent, sans ponctuation.

    « Soleil », « soleil » et « SOLEIL  » désignent la même position ; « Pare-soleil » et
    « Pare soleil » aussi.
    """
    sans_accent = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sans_accent.casefold()).strip("_")


def position_moyenne(positions: Iterable[float | None]) -> int | None:
    """Moyenne arrondie des positions connues (None si aucune n'est connue)."""
    connues = [float(p) for p in positions if p is not None]
    if not connues:
        return None
    return int(sum(connues) / len(connues) + 0.5)


def etat_groupe(etats: Sequence[str]) -> tuple[bool, bool, bool | None]:
    """(ouverture en cours, fermeture en cours, fermé) d'après l'état des volets disponibles.

    Le groupe est « fermé » quand tous ses volets le sont ; il est en mouvement dès qu'un volet
    l'est. Sans volet disponible, l'état de fermeture est inconnu (None).
    """
    if not etats:
        return False, False, None
    return "opening" in etats, "closing" in etats, all(e == "closed" for e in etats)


def regrouper_positions(
    par_volet: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Réunit les positions prédéfinies de plusieurs volets par nom.

    `par_volet` associe l'identifiant d'un volet à sa liste de positions (`name`, `position`,
    `icon` facultative). Le résultat associe la clé du nom à `{"nom", "icone", "volets"}`, où
    `volets` donne le pourcentage propre à chaque volet qui a cette position : un volet qui ne
    l'a pas n'y figure pas. Le nom affiché est celui du premier volet qui la porte.
    """
    reunies: dict[str, dict[str, Any]] = {}
    for volet, positions in par_volet.items():
        for ligne in positions:
            cle = cle_nom(str(ligne.get("name", "")))
            if not cle:
                continue
            groupe = reunies.setdefault(
                cle, {"nom": str(ligne["name"]).strip(), "icone": None, "volets": {}}
            )
            if groupe["icone"] is None and ligne.get("icon"):
                groupe["icone"] = str(ligne["icon"])
            groupe["volets"][volet] = round(float(ligne["position"]))
    return reunies
