"""Retrouver l'ouvrant d'origine, même après un renommage de son identifiant."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_SOURCE_ENTITY, CONF_SOURCE_ID


def id_source(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Identifiant actuel (cover.xxx) de l'ouvrant d'origine.

    On le retrouve par son identifiant interne du registre, qui ne change jamais, et non par
    son nom : l'utilisateur (ou l'échange de noms de cette intégration) peut le renommer.
    À défaut, on utilise l'identifiant enregistré à la création.
    """
    reglages = {**entry.data, **entry.options}
    interne = reglages.get(CONF_SOURCE_ID)
    if interne:
        trouvee = er.async_get(hass).async_get(interne)
        if trouvee is not None:
            return trouvee.entity_id
    return reglages[CONF_SOURCE_ENTITY]
