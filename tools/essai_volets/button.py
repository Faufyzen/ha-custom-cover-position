"""Un bouton « Identifier » par faux volet (il ne fait rien) : une autre entité de l'appareil source."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN
from .cover import NOMBRE


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([BoutonIdentifier(n) for n in range(1, NOMBRE + 1)])


class BoutonIdentifier(ButtonEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, numero: int) -> None:
        self._attr_name = "Identifier"
        self._attr_unique_id = f"essai3_volet_{numero}_identifier"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, f"volet_{numero}")})

    async def async_press(self) -> None:
        return None
