"""Boutons de positions prédéfinies d'un ouvrant (par exemple « Soleil » à 60 %).

Chaque position prédéfinie est un bouton rangé sous le même appareil que l'ouvrant, nommé
« <nom de l'ouvrant> <nom de la position> » (comme les boutons de modèle qu'il remplace) ;
il amène l'ouvrant à la position choisie. Les positions se gèrent dans les options de l'ouvrant.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import (
    CONF_NAME,
    CONF_PRESET_ICON,
    CONF_PRESET_NAME,
    CONF_PRESET_POSITION,
    CONF_PRESETS,
    DOMAIN,
)
from .cover import _appareil_de
from .source import id_source

_LOGGER = logging.getLogger(__name__)


def id_unique(entry: ConfigEntry, nom_position: str) -> str:
    """Identifiant unique du bouton : stable tant que le nom de la position ne change pas."""
    return f"{entry.entry_id}_position_{slugify(nom_position)}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée un bouton par position prédéfinie, et retire ceux d'une position supprimée."""
    reglages = {**entry.data, **entry.options}
    positions = reglages.get(CONF_PRESETS, [])
    registre = er.async_get(hass)

    voulus = {id_unique(entry, p[CONF_PRESET_NAME]) for p in positions}
    for entree in er.async_entries_for_config_entry(registre, entry.entry_id):
        if entree.domain == "button" and entree.unique_id not in voulus:
            registre.async_remove(entree.entity_id)

    boutons = []
    for position in positions:
        _preparer_registre(hass, entry, reglages[CONF_NAME], position)
        boutons.append(PositionPredefinie(hass, entry, reglages[CONF_NAME], position))
    async_add_entities(boutons)


def _preparer_registre(
    hass: HomeAssistant, entry: ConfigEntry, nom_ouvrant: str, position: dict
) -> None:
    """À la création du bouton, impose son nom et son identifiant (même raison que l'ouvrant).

    Rattaché à un appareil, un bouton prendrait « nom de l'appareil + nom du bouton » : on
    enregistre donc le nom voulu comme nom imposé, et l'identifiant en est déduit
    (`button.volet_chambre_chaleur`). Les changements faits ensuite par l'utilisateur sont respectés.
    """
    registre = er.async_get(hass)
    unique = id_unique(entry, position[CONF_PRESET_NAME])
    if registre.async_get_entity_id("button", DOMAIN, unique) is not None:
        return
    nom = f"{nom_ouvrant} {position[CONF_PRESET_NAME]}"
    creee = registre.async_get_or_create(
        "button",
        DOMAIN,
        unique,
        config_entry=entry,
        suggested_object_id=slugify(nom),
        original_name=nom,
        has_entity_name=False,
    )
    registre.async_update_entity(creee.entity_id, name=nom)


class PositionPredefinie(ButtonEntity):
    """Bouton qui amène l'ouvrant à une position choisie."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, nom_ouvrant: str, position: dict
    ) -> None:
        self._entry = entry
        self._position = int(position[CONF_PRESET_POSITION])
        self._attr_name = f"{nom_ouvrant} {position[CONF_PRESET_NAME]}"
        self._attr_unique_id = id_unique(entry, position[CONF_PRESET_NAME])
        self._attr_icon = position.get(CONF_PRESET_ICON) or "mdi:window-shutter-settings"
        # Même appareil que l'ouvrant d'origine, donc que l'ouvrant lui-même.
        self.device_entry = _appareil_de(hass, id_source(hass, entry))

    async def async_press(self) -> None:
        """Envoie l'ouvrant à la position, quel que soit son identifiant actuel."""
        identifiant = er.async_get(self.hass).async_get_entity_id(
            "cover", DOMAIN, self._entry.entry_id
        )
        if identifiant is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cover_not_found"
            )
        await self.hass.services.async_call(
            "cover",
            "set_cover_position",
            {"entity_id": identifiant, "position": self._position},
            blocking=True,
        )
