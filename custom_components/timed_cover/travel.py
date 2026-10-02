"""Estimation de la position d'un volet à partir de son temps de trajet.

Ce module ne dépend pas de Home Assistant : il se teste seul.

Convention : 0 = volet fermé, 100 = volet ouvert.

Principe : un volet qui monte de 0 à 100 en 40 secondes est, après 10 secondes de
montée, à la position 25. Le module ne connaît pas l'heure : l'appelant lui donne
l'instant courant (en secondes) à chaque question, ce qui rend les calculs
reproductibles dans les tests.
"""

from __future__ import annotations

from enum import Enum

POSITION_FERMEE = 0.0
POSITION_OUVERTE = 100.0

# Écart toléré (en secondes) entre l'heure d'arrivée calculée et l'heure réelle
# d'un minuteur : un minuteur peut se déclencher quelques millisecondes trop tôt.
TOLERANCE_ARRIVEE = 0.05


class Direction(Enum):
    """Sens de déplacement du volet."""

    ARRET = "arret"
    OUVERTURE = "ouverture"
    FERMETURE = "fermeture"


def _borne(position: float) -> float:
    """Ramène une position dans l'intervalle 0 à 100."""
    return max(POSITION_FERMEE, min(POSITION_OUVERTE, float(position)))


class TravelEstimator:
    """Calcule la position estimée d'un volet en mouvement."""

    def __init__(
        self,
        temps_montee: float,
        temps_descente: float,
        position: float = POSITION_FERMEE,
    ) -> None:
        """Crée l'estimateur ; les temps sont en secondes pour un trajet complet."""
        self.definir_temps(temps_montee, temps_descente)
        self._position = _borne(position)
        self._sens = Direction.ARRET
        self._cible = self._position
        self._debut = 0.0
        self._duree = 0.0

    # -- Réglages ---------------------------------------------------------

    def definir_temps(self, temps_montee: float, temps_descente: float) -> None:
        """Change les temps de trajet (ils s'appliquent aux prochains déplacements)."""
        if temps_montee <= 0 or temps_descente <= 0:
            raise ValueError("Les temps de trajet doivent être supérieurs à zéro.")
        self._temps_montee = float(temps_montee)
        self._temps_descente = float(temps_descente)

    @property
    def temps_montee(self) -> float:
        """Durée d'une ouverture complète, en secondes."""
        return self._temps_montee

    @property
    def temps_descente(self) -> float:
        """Durée d'une fermeture complète, en secondes."""
        return self._temps_descente

    # -- État -------------------------------------------------------------

    @property
    def sens(self) -> Direction:
        """Sens du déplacement en cours (ARRET si le volet est immobile)."""
        return self._sens

    @property
    def cible(self) -> float:
        """Position visée par le déplacement en cours."""
        return self._cible

    @property
    def en_mouvement(self) -> bool:
        """Vrai si un déplacement est en cours."""
        return self._sens is not Direction.ARRET

    def position(self, maintenant: float) -> float:
        """Position estimée à l'instant donné, entre 0 et 100 (décimale)."""
        if not self.en_mouvement:
            return self._position
        ecoule = max(0.0, maintenant - self._debut)
        if self._duree <= 0 or ecoule >= self._duree:
            return self._cible
        avancement = ecoule / self._duree
        return self._position + (self._cible - self._position) * avancement

    def position_arrondie(self, maintenant: float) -> int:
        """Position estimée arrondie à l'entier le plus proche."""
        return int(self.position(maintenant) + 0.5)

    def duree_vers(self, cible: float, depuis: float) -> float:
        """Durée (en secondes) pour aller de `depuis` à `cible`."""
        distance = _borne(cible) - _borne(depuis)
        if distance > 0:
            return distance / 100.0 * self._temps_montee
        if distance < 0:
            return -distance / 100.0 * self._temps_descente
        return 0.0

    def duree_restante(self, maintenant: float) -> float:
        """Secondes restant avant l'arrivée (0 si le volet est immobile)."""
        if not self.en_mouvement:
            return 0.0
        return max(0.0, self._debut + self._duree - maintenant)

    def est_arrive(self, maintenant: float) -> bool:
        """Vrai si le déplacement en cours est terminé (à la tolérance près)."""
        return self.en_mouvement and (
            maintenant - self._debut >= self._duree - TOLERANCE_ARRIVEE
        )

    # -- Actions ----------------------------------------------------------

    def demarrer(self, cible: float, maintenant: float) -> float:
        """Lance (ou relance) un déplacement vers `cible` ; renvoie sa durée.

        Si le volet bougeait déjà, la position du moment devient le point de départ.
        Si le volet est déjà à la cible, il ne bouge pas et la durée est nulle.
        """
        cible = _borne(cible)
        actuelle = self.position(maintenant)
        duree = self.duree_vers(cible, actuelle)
        self._position = actuelle
        self._debut = maintenant
        self._duree = duree
        if duree == 0.0:
            self._position = cible
            self._cible = cible
            self._sens = Direction.ARRET
            return 0.0
        self._cible = cible
        self._sens = Direction.OUVERTURE if cible > actuelle else Direction.FERMETURE
        return duree

    def arreter(self, maintenant: float) -> float:
        """Immobilise le volet à sa position du moment ; renvoie cette position."""
        actuelle = self.position(maintenant)
        self._position = actuelle
        self._cible = actuelle
        self._duree = 0.0
        self._sens = Direction.ARRET
        return actuelle

    def terminer(self) -> float:
        """Termine le déplacement : le volet est exactement à sa cible."""
        self._position = self._cible
        self._duree = 0.0
        self._sens = Direction.ARRET
        return self._position

    def definir_position(self, position: float) -> None:
        """Impose une position connue (recalage) et immobilise le volet."""
        self._position = _borne(position)
        self._cible = self._position
        self._duree = 0.0
        self._sens = Direction.ARRET
