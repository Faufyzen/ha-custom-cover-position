"""Groupe de volets : commande plusieurs entités personnalisées ensemble, chacune gardant sa position.

Un groupe est une entrée de configuration à part (`kind` = « group ») qui désigne des entités
personnalisées de l'intégration. Il crée sous son propre appareil :
- une entité cover : ouvrir, fermer, arrêter, aller à une position ;
- un bouton par nom de position trouvé chez ses volets (« Soleil », « Chaleur »…).

Choix de conception (détails dans le dépôt de contexte, fichier conception.md) :
- l'ordre est envoyé à tous les volets **en même temps** (un appel de service par volet, lancés
  ensemble), comme l'action `parallel:` d'un script : Overkiz fusionne alors les commandes en un
  seul envoi, et un volet n'attend jamais le suivant ;
- chaque volet calcule lui-même son trajet depuis sa propre position : le groupe ne calcule rien,
  il résume (position moyenne, état) ;
- un volet indisponible est ignoré (avertissement), une erreur sur un volet n'empêche pas les autres.
"""

from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.components.cover import (
    ATTR_CURRENT_POSITION,
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import EventStateChangedData, async_track_state_change_event
from homeassistant.util import slugify

from .agregat import etat_groupe, position_moyenne, regrouper_positions
from .const import (
    ATTR_MEMBERS,
    CONF_DEVICE_CLASS,
    CONF_KIND,
    CONF_MEMBERS,
    CONF_NAME,
    CONF_PRESETS,
    DOMAIN,
    KIND_GROUP,
    SERVICE_SET_KNOWN_POSITION,
)

_LOGGER = logging.getLogger(__name__)


def est_groupe(entry: ConfigEntry) -> bool:
    """Cette entrée est-elle un groupe ? (Les entrées d'avant les groupes n'ont pas de type.)"""
    return entry.data.get(CONF_KIND) == KIND_GROUP


def reglages(entry: ConfigEntry) -> dict[str, Any]:
    """Réglages du groupe (les options priment sur les données de création)."""
    return {**entry.data, **entry.options}


def entrees_membres(hass: HomeAssistant, entry: ConfigEntry) -> list[ConfigEntry]:
    """Entrées de configuration des volets du groupe qui existent encore."""
    trouvees = (
        hass.config_entries.async_get_entry(identifiant)
        for identifiant in reglages(entry).get(CONF_MEMBERS, [])
    )
    return [e for e in trouvees if e is not None and e.domain == DOMAIN and not est_groupe(e)]


def id_volet(hass: HomeAssistant, entree_membre: ConfigEntry) -> str | None:
    """Identifiant actuel (cover.xxx) d'un volet, même s'il a été renommé depuis."""
    return er.async_get(hass).async_get_entity_id("cover", DOMAIN, entree_membre.entry_id)


def ids_membres(hass: HomeAssistant, entry: ConfigEntry) -> list[str]:
    """Identifiants actuels des volets du groupe."""
    ids = (id_volet(hass, e) for e in entrees_membres(hass, entry))
    return [i for i in ids if i is not None]


def positions_regroupees(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    """Positions prédéfinies de tous les volets, réunies par nom (voir agregat.py)."""
    par_volet = {}
    for membre in entrees_membres(hass, entry):
        identifiant = id_volet(hass, membre)
        if identifiant is not None:
            par_volet[identifiant] = reglages(membre).get(CONF_PRESETS, [])
    return regrouper_positions(par_volet)


def entrees_des_groupes(hass: HomeAssistant) -> list[ConfigEntry]:
    return [e for e in hass.config_entries.async_entries(DOMAIN) if est_groupe(e)]


def surveiller_membres(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge le groupe quand les positions prédéfinies de ses volets changent de nom.

    Les boutons du groupe suivent les noms de position de ses volets : si l'un d'eux en ajoute,
    en retire ou en renomme une, les boutons doivent être recréés.
    """
    def signature() -> set[tuple[str, str | None]]:
        return {
            (cle, p["icone"]) for cle, p in positions_regroupees(hass, entry).items()
        }

    avant = signature()

    async def _un_volet_a_change(_hass: HomeAssistant, _membre: ConfigEntry) -> None:
        if signature() != avant:
            await hass.config_entries.async_reload(entry.entry_id)

    for membre in entrees_membres(hass, entry):
        entry.async_on_unload(membre.add_update_listener(_un_volet_a_change))


def retirer_des_groupes(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Quand un volet est supprimé, il sort de ses groupes (qui se rechargent alors)."""
    for groupe in entrees_des_groupes(hass):
        membres = reglages(groupe).get(CONF_MEMBERS, [])
        if entry.entry_id not in membres:
            continue
        restants = [m for m in membres if m != entry.entry_id]
        if CONF_MEMBERS in groupe.options:
            hass.config_entries.async_update_entry(
                groupe, options={**groupe.options, CONF_MEMBERS: restants}
            )
        else:
            hass.config_entries.async_update_entry(
                groupe, data={**groupe.data, CONF_MEMBERS: restants}
            )


def _appareil(entry: ConfigEntry, nom: str) -> DeviceInfo:
    """L'appareil du groupe, qui porte l'entité cover et les boutons."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=nom,
        manufacturer="Custom Cover Position",
        model="Group",
    )


def _imposer_nom(
    hass: HomeAssistant, entry: ConfigEntry, domaine: str, unique_id: str, nom: str
) -> None:
    """À la création, impose le nom et l'identifiant voulus (même raison que pour un volet).

    Rattachée à un appareil, une entité prendrait « nom de l'appareil + nom de l'entité » : le nom
    voulu est donc enregistré comme nom imposé, et l'identifiant en est déduit.
    """
    registre = er.async_get(hass)
    if registre.async_get_entity_id(domaine, DOMAIN, unique_id) is not None:
        return
    creee = registre.async_get_or_create(
        domaine,
        DOMAIN,
        unique_id,
        config_entry=entry,
        suggested_object_id=slugify(nom),
        original_name=nom,
        has_entity_name=False,
    )
    registre.async_update_entity(creee.entity_id, name=nom)


async def envoyer_en_parallele(
    hass: HomeAssistant,
    nom_groupe: str,
    commandes: list[tuple[str, str, str, dict[str, Any]]],
) -> None:
    """Envoie toutes les commandes (domaine, service, entité, données) en même temps.

    Les volets indisponibles sont ignorés avec un avertissement. Une erreur sur un volet
    disponible n'empêche pas les autres : elle est signalée à la fin, avec le nom du volet.
    """
    disponibles = []
    for commande in commandes:
        etat = hass.states.get(commande[2])
        if etat is None or etat.state == STATE_UNAVAILABLE:
            _LOGGER.warning("Groupe %s : %s est indisponible, il ne reçoit pas l'ordre.", nom_groupe, commande[2])
        else:
            disponibles.append(commande)
    if not disponibles:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="group_no_member",
            translation_placeholders={"name": nom_groupe},
        )

    debut = monotonic()

    async def _un_volet(domaine: str, service: str, entite: str, donnees: dict[str, Any]) -> None:
        await hass.services.async_call(
            domaine, service, {"entity_id": entite, **donnees}, blocking=True
        )
        _LOGGER.debug(
            "Groupe %s : %s.%s accepté par %s après %.0f ms",
            nom_groupe, domaine, service, entite, (monotonic() - debut) * 1000,
        )

    resultats = await asyncio.gather(
        *(_un_volet(*commande) for commande in disponibles), return_exceptions=True
    )
    echecs = []
    for commande, resultat in zip(disponibles, resultats):
        if isinstance(resultat, Exception):
            echecs.append((commande[2], resultat))
        elif isinstance(resultat, BaseException):
            raise resultat  # annulation : on la laisse passer
    if echecs:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="group_members_failed",
            translation_placeholders={
                "name": nom_groupe,
                "members": ", ".join(entite for entite, _ in echecs),
                "error": str(echecs[0][1]),
            },
        )


# -- Création des entités -------------------------------------------------------------------


def preparer_et_ajouter_cover(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    _imposer_nom(hass, entry, "cover", entry.entry_id, reglages(entry)[CONF_NAME])
    async_add_entities([GroupeOuvrants(hass, entry)])


def id_unique_bouton(entry: ConfigEntry, cle: str) -> str:
    return f"{entry.entry_id}_position_{cle}"


def preparer_et_ajouter_boutons(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Un bouton par nom de position des volets ; retire ceux d'une position qui a disparu."""
    nom_groupe = reglages(entry)[CONF_NAME]
    positions = positions_regroupees(hass, entry)
    registre = er.async_get(hass)
    voulus = {id_unique_bouton(entry, cle) for cle in positions}
    for entree in er.async_entries_for_config_entry(registre, entry.entry_id):
        if entree.domain == "button" and entree.unique_id not in voulus:
            registre.async_remove(entree.entity_id)
    boutons = []
    for cle, position in positions.items():
        _imposer_nom(
            hass, entry, "button", id_unique_bouton(entry, cle), f"{nom_groupe} {position['nom']}"
        )
        boutons.append(PositionGroupe(entry, nom_groupe, cle, position))
    async_add_entities(boutons)


# -- Les entités ------------------------------------------------------------------------------


class GroupeOuvrants(CoverEntity):
    """Entité cover d'un groupe : elle commande tous ses volets en même temps."""

    _attr_should_poll = False
    _attr_has_entity_name = False
    # La position est une estimation : les boutons Ouvrir / Fermer / Arrêter restent utilisables.
    _attr_assumed_state = True
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._nom = reglages(entry)[CONF_NAME]
        self._attr_name = self._nom
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = _appareil(entry, self._nom)
        self._suivis: list[str] = []
        self._annuler_suivi = None

    # -- Cycle de vie ------------------------------------------------------------------------

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._suivre()
        # Un volet renommé garde sa place dans le groupe : on suit son nouvel identifiant.
        self.async_on_remove(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registre_a_change)
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._annuler_suivi is not None:
            self._annuler_suivi()
            self._annuler_suivi = None

    def _suivre(self) -> None:
        """(Re)démarre la surveillance de l'état des volets."""
        if self._annuler_suivi is not None:
            self._annuler_suivi()
        self._suivis = ids_membres(self.hass, self._entry)
        self._annuler_suivi = async_track_state_change_event(
            self.hass, self._suivis, self._un_volet_a_change
        )

    @callback
    def _registre_a_change(self, event: Event) -> None:
        if event.data.get("old_entity_id") in self._suivis:
            self._suivre()
            self.async_write_ha_state()

    @callback
    def _un_volet_a_change(self, _event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    # -- Informations ------------------------------------------------------------------------

    def _etats_disponibles(self) -> list[State]:
        etats = (self.hass.states.get(i) for i in ids_membres(self.hass, self._entry))
        return [e for e in etats if e is not None and e.state != STATE_UNAVAILABLE]

    @property
    def available(self) -> bool:
        """Disponible tant qu'au moins un volet du groupe l'est."""
        return bool(self._etats_disponibles())

    @property
    def current_cover_position(self) -> int | None:
        """Position moyenne des volets : exacte quand ils sont tous au même endroit."""
        return position_moyenne(
            e.attributes.get(ATTR_CURRENT_POSITION) for e in self._etats_disponibles()
        )

    @property
    def is_opening(self) -> bool:
        return etat_groupe([e.state for e in self._etats_disponibles()])[0]

    @property
    def is_closing(self) -> bool:
        return etat_groupe([e.state for e in self._etats_disponibles()])[1]

    @property
    def is_closed(self) -> bool | None:
        return etat_groupe([e.state for e in self._etats_disponibles()])[2]

    @property
    def device_class(self) -> str | None:
        """Classe commune des volets, quand ils en ont tous la même."""
        classes = {e.attributes.get(CONF_DEVICE_CLASS) for e in self._etats_disponibles()}
        return classes.pop() if len(classes) == 1 else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_MEMBERS: ids_membres(self.hass, self._entry)}

    # -- Ordres reçus de Home Assistant ------------------------------------------------------

    async def _a_tous(self, service: str, domaine: str = "cover", **donnees: Any) -> None:
        commandes = [
            (domaine, service, identifiant, donnees)
            for identifiant in ids_membres(self.hass, self._entry)
        ]
        await envoyer_en_parallele(self.hass, self._nom, commandes)

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._a_tous("open_cover")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._a_tous("close_cover")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._a_tous("stop_cover")

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        """Le même pourcentage pour tous : chaque volet part de sa propre position."""
        await self._a_tous("set_cover_position", position=kwargs[ATTR_POSITION])

    async def async_set_known_position(self, position: int) -> None:
        """Recale la position de tous les volets (service timed_cover.set_known_position)."""
        await self._a_tous(SERVICE_SET_KNOWN_POSITION, domaine=DOMAIN, position=position)


class PositionGroupe(ButtonEntity):
    """Bouton du groupe : envoie chaque volet qui a cette position à son propre pourcentage."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(
        self, entry: ConfigEntry, nom_groupe: str, cle: str, position: dict[str, Any]
    ) -> None:
        self._entry = entry
        self._nom_groupe = nom_groupe
        self._cle = cle
        self._attr_name = f"{nom_groupe} {position['nom']}"
        self._attr_unique_id = id_unique_bouton(entry, cle)
        self._attr_icon = position["icone"] or "mdi:window-shutter-settings"
        self._attr_device_info = _appareil(entry, nom_groupe)

    async def async_press(self) -> None:
        """Lit les positions au moment de l'appui : elles ont pu changer depuis la création."""
        volets = positions_regroupees(self.hass, self._entry).get(self._cle, {}).get("volets", {})
        commandes = [
            ("cover", "set_cover_position", identifiant, {ATTR_POSITION: pourcentage})
            for identifiant, pourcentage in volets.items()
        ]
        await envoyer_en_parallele(self.hass, self._nom_groupe, commandes)
