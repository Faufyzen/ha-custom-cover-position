"""Faux volets pour mesurer le parallélisme des ordres (outil de test, non distribué).

Huit volets « Essai volet 1 » à « Essai volet 8 » qui se comportent comme des volets RTS :
ouvrir, fermer, arrêter, aucune position, état « inconnu ». Chacun note dans un journal
l'instant où il REÇOIT un ordre, puis attend un délai réglable avant de l'ACCEPTER (comme
l'envoi d'une commande à Overkiz). Ce journal dit si des ordres arrivent ensemble ou l'un après
l'autre, ce que les faux volets de `demo` (instantanés) ne permettent pas de distinguer.

Services : essai_volets.configurer (delai en secondes), essai_volets.vider,
essai_volets.journal (renvoie la liste des ordres avec leurs instants).
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse

DOMAIN = "essai_volets"
PLATFORMS = [Platform.COVER, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    donnees = hass.data.setdefault(DOMAIN, {"journal": [], "delai": 1.0})

    async def configurer(appel: ServiceCall) -> None:
        donnees["delai"] = float(appel.data["delai"])

    async def vider(appel: ServiceCall) -> None:
        donnees["journal"].clear()

    async def journal(appel: ServiceCall) -> ServiceResponse:
        return {"ordres": [dict(o) for o in donnees["journal"]], "delai": donnees["delai"]}

    hass.services.async_register(
        DOMAIN, "configurer", configurer, vol.Schema({vol.Required("delai"): vol.Coerce(float)})
    )
    hass.services.async_register(DOMAIN, "vider", vider)
    hass.services.async_register(
        DOMAIN, "journal", journal, supports_response=SupportsResponse.ONLY
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        for nom in ("configurer", "vider", "journal"):
            hass.services.async_remove(DOMAIN, nom)
        hass.data.pop(DOMAIN, None)
        return True
    return False
