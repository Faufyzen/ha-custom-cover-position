"""Les faux volets : ils notent l'instant de réception de chaque ordre."""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Any

from homeassistant.components.cover import CoverEntity, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN

PARALLEL_UPDATES = 0  # comme la plateforme cover d'Overkiz : aucun verrou entre volets
NOMBRE = 8


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([VoletEssai(hass, n) for n in range(1, NOMBRE + 1)])


class VoletEssai(CoverEntity):
    """Volet sans retour d'état (RTS) : ouvrir, fermer, arrêter."""

    _attr_should_poll = False
    _attr_has_entity_name = True  # le nom de l'entité est celui de l'appareil : cover.essai_volet_N
    _attr_is_closed = None  # état « inconnu », comme un volet RTS
    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    )

    def __init__(self, hass: HomeAssistant, numero: int) -> None:
        self._donnees = hass.data[DOMAIN]
        self._numero = numero
        self._attr_name = None
        self._attr_unique_id = f"essai3_volet_{numero}"
        # Un appareil par volet, avec un bouton « Identifier » comme chez Overkiz : il permet
        # d'essayer la désactivation des autres entités de l'appareil source.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"volet_{numero}")}, name=f"Essai volet {numero}"
        )

    async def _recevoir(self, ordre: str) -> None:
        entree = {"volet": self._numero, "ordre": ordre, "recu": monotonic()}
        self._donnees["journal"].append(entree)
        await asyncio.sleep(self._donnees["delai"])
        entree["accepte"] = monotonic()

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._recevoir("open")

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._recevoir("close")

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._recevoir("stop")
