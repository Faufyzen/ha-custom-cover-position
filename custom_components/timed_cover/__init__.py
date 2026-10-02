"""Intégration « Volets à temps de trajet » (timed_cover).

Elle enrobe une entité cover existante (par exemple un volet Overkiz) pour lui ajouter
une position estimée à partir de ses temps de montée et de descente.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import CONF_HIDE_SOURCE, CONF_SOURCE_ENTITY, DEFAULT_HIDE_SOURCE

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Prépare un volet à temps de trajet à partir de son entrée de configuration."""
    source = entry.data[CONF_SOURCE_ENTITY]

    # Au démarrage de Home Assistant, l'entité à enrober peut ne pas encore exister :
    # on laisse Home Assistant réessayer plus tard plutôt que d'échouer.
    if er.async_get(hass).async_get(source) is None and hass.states.get(source) is None:
        raise ConfigEntryNotReady(f"L'entité {source} n'est pas encore disponible.")

    _regler_masquage_source(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Quand les options changent (temps de trajet, etc.), on recharge l'entrée.
    entry.async_on_unload(entry.add_update_listener(_recharger_apres_modification))
    return True


async def _recharger_apres_modification(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge l'entrée après une modification des options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge un volet à temps de trajet."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _regler_masquage_source(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Masque (ou ré-affiche) le volet d'origine selon l'option choisie.

    Un volet masqué n'apparaît plus dans l'interface, mais reste utilisable en interne :
    c'est ce que fait notre volet pour lui envoyer ses ordres. On ne ré-affiche que
    ce que l'intégration avait elle-même masqué, jamais un choix de l'utilisateur.
    """
    registre = er.async_get(hass)
    source = registre.async_get(entry.data[CONF_SOURCE_ENTITY])
    if source is None:
        return
    reglages = {**entry.data, **entry.options}
    if reglages.get(CONF_HIDE_SOURCE, DEFAULT_HIDE_SOURCE):
        if source.hidden_by is None:
            registre.async_update_entity(
                source.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
            )
    elif source.hidden_by is er.RegistryEntryHider.INTEGRATION:
        registre.async_update_entity(source.entity_id, hidden_by=None)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """À la suppression du volet à temps de trajet, ré-affiche le volet d'origine."""
    registre = er.async_get(hass)
    source = registre.async_get(entry.data[CONF_SOURCE_ENTITY])
    if source is not None and source.hidden_by is er.RegistryEntryHider.INTEGRATION:
        registre.async_update_entity(source.entity_id, hidden_by=None)
