"""Diagnostic d'un ouvrant à position estimée.

Les noms de champs sont en anglais et sans accent : le fichier peut être partagé tel quel
(un forum, un dépôt public) et s'affiche correctement partout.

C'est le fichier que propose « Télécharger les diagnostics », dans le menu ⋮ de l'ouvrant sur la page
de l'intégration. Il rassemble tout ce qu'il faut pour comprendre un problème sans décrire l'écran :
la configuration, l'état de l'ouvrant et de l'ouvrant d'origine, les boutons de positions et
l'état du registre. La configuration de l'intégration ne contient aucun secret (pas de mot de
passe ni de jeton) : rien n'a besoin d'être masqué.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import __version__ as VERSION_HA
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.loader import async_get_integration

from . import groupe
from .const import DOMAIN
from .source import id_source


def _valeur(enum: Any) -> str | None:
    """Texte d'une valeur énumérée du registre (ou None)."""
    return None if enum is None else str(getattr(enum, "value", enum))


def _etat(hass: HomeAssistant, entity_id: str | None) -> dict[str, Any] | None:
    """État actuel d'une entité, tel que Home Assistant le connaît."""
    etat = hass.states.get(entity_id) if entity_id else None
    if etat is None:
        return None
    return {
        "entity_id": entity_id,
        "state": etat.state,
        "attributes": dict(etat.attributes),
        "last_changed": etat.last_changed.isoformat(),
    }


def _registre(entree: er.RegistryEntry | None) -> dict[str, Any] | None:
    """Ce que le registre des entités retient d'une entité."""
    if entree is None:
        return None
    return {
        "entity_id": entree.entity_id,
        "platform": entree.platform,
        "name_set_by_user": entree.name,
        "original_name": entree.original_name,
        "hidden_by": _valeur(entree.hidden_by),
        "disabled_by": _valeur(entree.disabled_by),
        "device_id": entree.device_id,
        "options": {domain: dict(values) for domain, values in entree.options.items()},
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Diagnostic de l'ouvrant correspondant à cette entrée de configuration."""
    registre = er.async_get(hass)
    integration = await async_get_integration(hass, DOMAIN)
    if groupe.est_groupe(entry):
        identifiant_groupe = registre.async_get_entity_id("cover", DOMAIN, entry.entry_id)
        return {
            "versions": {"integration": str(integration.version), "home_assistant": VERSION_HA},
            "config_entry": {
                "title": entry.title,
                "format_version": entry.version,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "cover": {
                "state": _etat(hass, identifiant_groupe),
                "registry": _registre(registre.async_get(identifiant_groupe)),
            },
            "members": [
                {"state": _etat(hass, i), "registry": _registre(registre.async_get(i))}
                for i in groupe.ids_membres(hass, entry)
            ],
            "preset_buttons": [
                {"state": _etat(hass, e.entity_id), "registry": _registre(e)}
                for e in er.async_entries_for_config_entry(registre, entry.entry_id)
                if e.domain == "button"
            ],
        }
    identifiant_source = id_source(hass, entry)
    identifiant_ouvrant = registre.async_get_entity_id("cover", DOMAIN, entry.entry_id)
    source = registre.async_get(identifiant_source)
    autres_entites = []
    if source is not None and source.device_id is not None:
        autres_entites = [
            {**(_registre(e) or {}), "state": getattr(hass.states.get(e.entity_id), "state", None)}
            for e in er.async_entries_for_device(
                registre, source.device_id, include_disabled_entities=True
            )
            if e.id != source.id and e.platform != DOMAIN
        ]
    return {
        "versions": {"integration": str(integration.version), "home_assistant": VERSION_HA},
        "config_entry": {
            "title": entry.title,
            "format_version": entry.version,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "cover": {
            "state": _etat(hass, identifiant_ouvrant),
            "registry": _registre(registre.async_get(identifiant_ouvrant)),
        },
        "source_cover": {
            "state": _etat(hass, identifiant_source),
            "registry": _registre(source),
        },
        "preset_buttons": [
            {"state": _etat(hass, e.entity_id), "registry": _registre(e)}
            for e in er.async_entries_for_config_entry(registre, entry.entry_id)
            if e.domain == "button"
        ],
        "other_entities_of_source_device": autres_entites,
    }
