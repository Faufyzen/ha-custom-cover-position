"""Intégration « Custom Cover Position » (timed_cover).

Elle enrobe une entité cover existante (par exemple un volet Overkiz) pour lui ajouter
une position estimée à partir de ses temps d'ouverture et de fermeture complètes.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify

from .const import (
    CONF_HIDE_SOURCE,
    CONF_NAME,
    CONF_RESTORE,
    CONF_SOURCE_ENTITY,
    CONF_SOURCE_ID,
    CONF_SOURCE_SUFFIX,
    CONF_TAKE_OVER,
    DEFAULT_HIDE_SOURCE,
    DEFAULT_TAKE_OVER,
    DOMAIN,
)
from .source import id_source

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.COVER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Prépare un ouvrant à position estimée à partir de son entrée de configuration."""
    _memoriser_id_interne(hass, entry)
    source = id_source(hass, entry)

    # Au démarrage de Home Assistant, l'entité à enrober peut ne pas encore exister :
    # on laisse Home Assistant réessayer plus tard plutôt que d'échouer.
    if er.async_get(hass).async_get(source) is None and hass.states.get(source) is None:
        raise ConfigEntryNotReady(f"L'entité {source} n'est pas encore disponible.")

    _echanger_les_noms(hass, entry)
    _regler_masquage_source(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Quand les options changent (temps d'ouverture, etc.), on recharge l'entrée.
    entry.async_on_unload(entry.add_update_listener(_recharger_apres_modification))
    return True


async def _recharger_apres_modification(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Recharge l'entrée après une modification des options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge un ouvrant à position estimée."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _memoriser_id_interne(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Complète une entrée créée avant l'identifiant interne (elle ne le connaissait pas)."""
    if entry.data.get(CONF_SOURCE_ID):
        return
    source = er.async_get(hass).async_get(entry.data[CONF_SOURCE_ENTITY])
    if source is not None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SOURCE_ID: source.id}
        )


def _echanger_les_noms(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """À la première mise en route, l'ouvrant d'origine cède son nom et son identifiant.

    L'ouvrant d'origine est renommé avec le suffixe choisi (« Volet Cuisine (origine) »,
    `cover.volet_cuisine_origine`) et le nouvel ouvrant prend son nom et son identifiant : les
    scripts et automatisations qui visent `cover.volet_cuisine` utilisent alors le nouvel
    ouvrant, sans modification. L'échange n'a lieu que si l'identifiant voulu est justement
    celui de l'ouvrant d'origine, et une seule fois (ce qu'il faudra remettre en état à la
    suppression est gardé dans l'entrée).
    """
    reglages = {**entry.data, **entry.options}
    if not reglages.get(CONF_TAKE_OVER, DEFAULT_TAKE_OVER) or entry.data.get(CONF_RESTORE):
        return
    registre = er.async_get(hass)
    source = registre.async_get(id_source(hass, entry))
    if source is None:
        return  # ouvrant sans identifiant unique : il ne peut pas être renommé
    nom = reglages[CONF_NAME]
    suffixe = reglages.get(CONF_SOURCE_SUFFIX, "")
    if source.entity_id != f"cover.{slugify(nom)}" or not slugify(suffixe):
        return  # pas de conflit d'identifiant : rien à échanger
    nouvel_id = registre.async_generate_entity_id(
        "cover", f"{slugify(nom)}_{slugify(suffixe)}"
    )
    nouveau_nom = f"{nom} ({suffixe})"
    registre.async_update_entity(source.entity_id, new_entity_id=nouvel_id, name=nouveau_nom)
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_SOURCE_ENTITY: nouvel_id,
            CONF_RESTORE: {
                "old_entity_id": source.entity_id,
                "new_entity_id": nouvel_id,
                "old_name": source.name,  # nom imposé par l'utilisateur, souvent None
                "new_name": nouveau_nom,
            },
        },
    )
    _LOGGER.info("%s renommé en %s pour laisser sa place à %s", source.entity_id, nouvel_id, nom)


def _regler_masquage_source(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Masque (ou ré-affiche) l'ouvrant d'origine selon l'option choisie.

    Un ouvrant masqué n'apparaît plus dans les écrans automatiques, mais reste utilisable en
    interne : c'est ce que fait notre ouvrant pour lui envoyer ses ordres. On ne ré-affiche
    que ce que l'intégration avait elle-même masqué, jamais un choix de l'utilisateur.
    """
    registre = er.async_get(hass)
    source = registre.async_get(id_source(hass, entry))
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
    """À la suppression : l'ouvrant d'origine retrouve son nom, son identifiant et sa visibilité.

    On ne remet en état que ce que l'intégration avait elle-même changé : un nom ou un
    identifiant modifié depuis par l'utilisateur est respecté.
    """
    registre = er.async_get(hass)
    source = registre.async_get(id_source(hass, entry))
    if source is None:
        return
    modifications: dict = {}
    restaurer = entry.data.get(CONF_RESTORE)
    if restaurer:
        # Le nouvel ouvrant tient encore l'identifiant d'origine : on le libère d'abord.
        nouveau = registre.async_get_entity_id("cover", DOMAIN, entry.entry_id)
        if nouveau is not None:
            registre.async_remove(nouveau)
        if source.entity_id == restaurer["new_entity_id"]:
            modifications["new_entity_id"] = restaurer["old_entity_id"]
        if source.name == restaurer["new_name"]:
            modifications["name"] = restaurer["old_name"]
    if source.hidden_by is er.RegistryEntryHider.INTEGRATION:
        modifications["hidden_by"] = None
    if modifications:
        registre.async_update_entity(source.entity_id, **modifications)
