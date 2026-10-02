"""Entité ouvrant à position estimée.

L'ouvrant réel (par exemple un volet Overkiz) ne connaît pas sa position : on lui
envoie des ordres « ouvrir », « fermer » et « arrêter », et on estime sa position
d'après le temps écoulé (voir travel.py).

Choix de conception (détails dans le dépôt de contexte, fichier conception.md) :
- chaque volet est indépendant (aucun état partagé) et possède un verrou, pour que
  des ordres reçus en même temps (script de groupe) ne se mélangent pas ;
- pour aller à une position intermédiaire, l'ordre d'arrêt est programmé à l'instant
  calculé (minuteur), plutôt que par une boucle de surveillance ;
- le décompte du temps démarre quand l'ordre a été accepté par le volet réel ;
- les ordres « ouvrir » et « fermer » sont toujours envoyés, même si la position
  estimée est déjà à l'extrémité : cela permet de recaler un volet qui a dérivé.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from time import monotonic
from typing import Any

import voluptuous as vol

from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify

from .const import (
    ATTR_SOURCE_ENTITY,
    ATTR_TARGET_POSITION,
    ATTR_TRAVEL_TIME_DOWN,
    ATTR_TRAVEL_TIME_UP,
    CONF_DEVICE_CLASS,
    CONF_NAME,
    CONF_SEND_STOP_AT_ENDS,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_SEND_STOP_AT_ENDS,
    DOMAIN,
    SERVICE_SET_KNOWN_POSITION,
)
from .source import id_source
from .travel import POSITION_OUVERTE, Direction, TravelEstimator

_LOGGER = logging.getLogger(__name__)

# Pendant un déplacement, la position affichée est rafraîchie à cet intervalle.
INTERVALLE_AFFICHAGE = timedelta(seconds=1)

# Écart (en points de pourcentage) en dessous duquel on considère être déjà à la cible.
ECART_CIBLE = 0.5


def _appareil_de(hass: HomeAssistant, entity_id: str):
    """Renvoie l'appareil de l'entité à enrober (ou None s'il n'en a pas).

    Les règles de Home Assistant (depuis 2025.7, obligatoires depuis 2026.8) demandent à
    une entité qui enrobe une autre de se rattacher à l'appareil de celle-ci en renseignant
    `device_entry`, sans jamais ajouter sa propre entrée de configuration à cet appareil.
    """
    try:
        from homeassistant.helpers.device import async_entity_id_to_device
    except ImportError:  # version de Home Assistant sans cette fonction
        _LOGGER.warning(
            "Impossible de rattacher %s à l'appareil du volet : fonction absente de "
            "cette version de Home Assistant.",
            entity_id,
        )
        return None
    try:
        return async_entity_id_to_device(hass, entity_id)
    except (vol.Invalid, KeyError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Ajoute l'ouvrant à position estimée d'une entrée de configuration."""
    _preparer_registre(hass, entry)
    async_add_entities([OuvrantPositionEstimee(hass, entry)])

    plateforme = entity_platform.async_get_current_platform()
    plateforme.async_register_entity_service(
        SERVICE_SET_KNOWN_POSITION,
        {vol.Required(ATTR_POSITION): vol.All(vol.Coerce(int), vol.Range(min=0, max=100))},
        "async_set_known_position",
    )


def _preparer_registre(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """À la toute première création, impose le nom et l'identifiant choisis par l'utilisateur.

    Depuis Home Assistant 2026.8, une entité rattachée à un appareil prend pour nom
    « nom de l'appareil + nom de l'entité » (et pour identifiant le même assemblage) :
    un volet nommé « Volet Salon 1 » sous l'appareil « Volet Salon 1 [overkiz] » deviendrait
    « Volet Salon 1 [overkiz] Volet Salon 1 ». Le nom saisi dans le formulaire est donc
    enregistré comme nom imposé par l'utilisateur, et l'identifiant en est déduit.
    Cela ne se fait qu'à la création : les modifications faites ensuite par l'utilisateur
    dans les réglages de l'entité sont respectées.
    """
    registre = er.async_get(hass)
    if registre.async_get_entity_id("cover", DOMAIN, entry.entry_id) is not None:
        return
    reglages = {**entry.data, **entry.options}
    nom = reglages[CONF_NAME]
    creee = registre.async_get_or_create(
        "cover",
        DOMAIN,
        entry.entry_id,
        config_entry=entry,
        suggested_object_id=slugify(nom),
        original_name=nom,
        has_entity_name=False,
    )
    registre.async_update_entity(creee.entity_id, name=nom)


class OuvrantPositionEstimee(CoverEntity, RestoreEntity):
    """Ouvrant dont la position est estimée à partir de ses temps d'ouverture et de fermeture."""

    _attr_should_poll = False
    _attr_has_entity_name = False
    # La position est une estimation : Home Assistant garde donc les boutons
    # Ouvrir / Fermer / Arrêter toujours utilisables.
    _attr_assumed_state = True
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Prépare l'entité à partir de la configuration (options prioritaires)."""
        reglages = {**entry.data, **entry.options}
        self._entry = entry
        self._envoyer_stop_aux_extremites: bool = reglages.get(
            CONF_SEND_STOP_AT_ENDS, DEFAULT_SEND_STOP_AT_ENDS
        )
        self._estimateur = TravelEstimator(
            reglages[CONF_TRAVEL_TIME_UP], reglages[CONF_TRAVEL_TIME_DOWN]
        )
        self._verrou = asyncio.Lock()
        self._annuler_arret: Callable[[], None] | None = None
        self._annuler_rafraichissement: Callable[[], None] | None = None
        self._annuler_suivi: Callable[[], None] | None = None
        self._suivi_id: str | None = None

        self._attr_name = reglages[CONF_NAME]
        self._attr_unique_id = entry.entry_id
        self._attr_device_class = reglages.get(CONF_DEVICE_CLASS, DEFAULT_DEVICE_CLASS)
        # Rattachement à l'appareil du volet réel (modèle recommandé par Home Assistant).
        self.device_entry = _appareil_de(hass, id_source(hass, entry))

    @property
    def _source(self) -> str:
        """Identifiant actuel de l'ouvrant d'origine (suit un éventuel renommage)."""
        return id_source(self.hass, self._entry)

    # -- Cycle de vie -----------------------------------------------------

    async def async_added_to_hass(self) -> None:
        """Restaure la dernière position et surveille la disponibilité du volet réel."""
        await super().async_added_to_hass()
        ancien = await self.async_get_last_state()
        if ancien is not None:
            position = ancien.attributes.get(ATTR_CURRENT_POSITION)
            if position is not None:
                try:
                    self._estimateur.definir_position(float(position))
                except (TypeError, ValueError):
                    _LOGGER.debug("Position restaurée illisible : %s", position)
        self._suivre_source()
        # Si l'ouvrant d'origine est renommé, on suit son nouvel identifiant.
        self.async_on_remove(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED, self._registre_a_change
            )
        )

    def _suivre_source(self) -> None:
        """(Re)démarre la surveillance de l'état de l'ouvrant d'origine."""
        if self._annuler_suivi is not None:
            self._annuler_suivi()
        self._suivi_id = self._source
        self._annuler_suivi = async_track_state_change_event(
            self.hass, [self._suivi_id], self._source_a_change
        )

    @callback
    def _registre_a_change(self, event: Event) -> None:
        """Le registre a changé : si c'est l'identifiant de l'ouvrant d'origine, on le suit."""
        if event.data.get("old_entity_id") == self._suivi_id:
            self._suivre_source()
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Arrête les minuteurs et la surveillance quand l'entité est retirée."""
        self._arreter_minuteurs()
        if self._annuler_suivi is not None:
            self._annuler_suivi()
            self._annuler_suivi = None

    @callback
    def _source_a_change(self, _event: Event[EventStateChangedData]) -> None:
        """L'ouvrant réel a changé d'état : on met à jour la disponibilité."""
        self.async_write_ha_state()

    # -- Informations -----------------------------------------------------

    @property
    def available(self) -> bool:
        """Disponible tant que le volet réel existe et n'est pas « indisponible ».

        L'état « inconnu » reste disponible : les volets RTS n'ont aucun retour d'état,
        leur état est « inconnu » en permanence, ce qui est normal.
        """
        etat = self.hass.states.get(self._source)
        return etat is not None and etat.state != STATE_UNAVAILABLE

    @property
    def current_cover_position(self) -> int:
        """Position estimée (0 = fermé, 100 = ouvert)."""
        return self._estimateur.position_arrondie(monotonic())

    @property
    def is_closed(self) -> bool:
        """Fermé quand le volet est immobile à la position 0."""
        return not self._estimateur.en_mouvement and self.current_cover_position == 0

    @property
    def is_opening(self) -> bool:
        """Ouverture en cours."""
        return self._estimateur.sens is Direction.OUVERTURE

    @property
    def is_closing(self) -> bool:
        """Fermeture en cours."""
        return self._estimateur.sens is Direction.FERMETURE

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Informations affichées en plus de l'état."""
        attributs: dict[str, Any] = {
            ATTR_SOURCE_ENTITY: self._source,
            ATTR_TRAVEL_TIME_UP: self._estimateur.temps_montee,
            ATTR_TRAVEL_TIME_DOWN: self._estimateur.temps_descente,
        }
        if self._estimateur.en_mouvement:
            attributs[ATTR_TARGET_POSITION] = round(self._estimateur.cible)
        return attributs

    # -- Ordres reçus de Home Assistant -----------------------------------

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Ouvre complètement le volet."""
        await self._aller_a(POSITION_OUVERTE, toujours_envoyer=True)

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Ferme complètement le volet."""
        await self._aller_a(0.0, toujours_envoyer=True)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Amène le volet à une position intermédiaire."""
        await self._aller_a(float(kwargs[ATTR_POSITION]))

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Arrête le volet à sa position du moment."""
        async with self._verrou:
            await self._arreter_verrouille()
            self.async_write_ha_state()

    async def async_set_known_position(self, position: int) -> None:
        """Recale la position estimée (service timed_cover.set_known_position)."""
        async with self._verrou:
            self._arreter_minuteurs()
            self._estimateur.definir_position(position)
            self.async_write_ha_state()

    # -- Mécanique interne ------------------------------------------------

    async def _appeler_source(self, service: str) -> None:
        """Envoie un ordre au volet réel et attend qu'il l'ait accepté."""
        if not self.available:
            raise HomeAssistantError(
                f"L'ouvrant « {self.name} » est indisponible : {self._source} ne répond pas."
            )
        await self.hass.services.async_call(
            "cover", service, {"entity_id": self._source}, blocking=True
        )

    async def _aller_a(self, cible: float, *, toujours_envoyer: bool = False) -> None:
        """Déplace le volet vers `cible` (0 à 100)."""
        async with self._verrou:
            maintenant = monotonic()
            actuelle = self._estimateur.position(maintenant)
            sens_voulu = Direction.OUVERTURE if cible > actuelle else Direction.FERMETURE

            if self._estimateur.en_mouvement:
                if self._estimateur.sens is sens_voulu and abs(cible - actuelle) >= ECART_CIBLE:
                    # Le volet va déjà dans le bon sens : seule l'heure d'arrêt change,
                    # aucun nouvel ordre n'est envoyé.
                    duree = self._estimateur.demarrer(cible, maintenant)
                    self._programmer_arret(duree)
                    self.async_write_ha_state()
                    return
                # Demi-tour ou cible déjà atteinte : on arrête d'abord le volet.
                await self._arreter_verrouille()
                maintenant = monotonic()
                actuelle = self._estimateur.position(maintenant)

            if abs(cible - actuelle) < ECART_CIBLE:
                if toujours_envoyer:
                    # Recalage : l'ordre part quand même, la position reste à l'extrémité.
                    await self._appeler_source(
                        "open_cover" if cible >= POSITION_OUVERTE else "close_cover"
                    )
                self._estimateur.definir_position(cible)
                self.async_write_ha_state()
                return

            service = "open_cover" if cible > actuelle else "close_cover"
            await self._appeler_source(service)
            # Le décompte démarre quand l'ordre a été accepté.
            duree = self._estimateur.demarrer(cible, monotonic())
            self._programmer_arret(duree)
            self._demarrer_rafraichissement()
            self.async_write_ha_state()

    async def _arreter_verrouille(self) -> None:
        """Arrête le volet (le verrou doit déjà être pris par l'appelant)."""
        self._arreter_minuteurs()
        self._estimateur.arreter(monotonic())
        await self._appeler_source("stop_cover")

    def _programmer_arret(self, duree: float) -> None:
        """Programme l'arrivée du volet à sa cible, dans `duree` secondes."""
        self._annuler_minuteur_arret()
        self._annuler_arret = async_call_later(self.hass, duree, self._arrivee)

    async def _arrivee(self, _maintenant: datetime) -> None:
        """Le temps de trajet est écoulé : le volet est arrivé à sa cible."""
        self._annuler_arret = None
        async with self._verrou:
            maintenant = monotonic()
            if not self._estimateur.en_mouvement:
                return  # un autre ordre est passé entre-temps
            restant = self._estimateur.duree_restante(maintenant)
            if restant > 0.05:
                # Minuteur déclenché trop tôt, ou nouvelle cible : on attend le reste.
                self._programmer_arret(restant)
                return
            cible = self._estimateur.cible
            self._estimateur.terminer()
            self._arreter_rafraichissement()
            aux_extremites = cible <= 0 or cible >= POSITION_OUVERTE
            if not aux_extremites or self._envoyer_stop_aux_extremites:
                try:
                    await self._appeler_source("stop_cover")
                except HomeAssistantError as erreur:
                    _LOGGER.error(
                        "Le volet %s est arrivé à %s %% mais l'ordre d'arrêt a échoué : %s",
                        self.name,
                        round(cible),
                        erreur,
                    )
            self.async_write_ha_state()

    def _demarrer_rafraichissement(self) -> None:
        """Rafraîchit la position affichée pendant le déplacement."""
        if self._annuler_rafraichissement is None:
            self._annuler_rafraichissement = async_track_time_interval(
                self.hass, self._rafraichir, INTERVALLE_AFFICHAGE
            )

    @callback
    def _rafraichir(self, _maintenant: datetime) -> None:
        """Met à jour l'affichage (appelé chaque seconde pendant un déplacement)."""
        self.async_write_ha_state()

    def _arreter_rafraichissement(self) -> None:
        if self._annuler_rafraichissement is not None:
            self._annuler_rafraichissement()
            self._annuler_rafraichissement = None

    def _annuler_minuteur_arret(self) -> None:
        if self._annuler_arret is not None:
            self._annuler_arret()
            self._annuler_arret = None

    def _arreter_minuteurs(self) -> None:
        """Annule tous les minuteurs de l'entité."""
        self._annuler_minuteur_arret()
        self._arreter_rafraichissement()
