"""Étapes de configuration d'un volet à temps de trajet.

Création : deux étapes.
  1. choisir l'ouvrant réel à enrober (par exemple le volet Overkiz) ;
  2. donner un nom, les temps d'ouverture et de fermeture, et l'échange des noms.
Options (bouton « Configurer » de l'entrée) : temps, ordre d'arrêt aux extrémités, classe d'appareil,
masquage de l'ouvrant d'origine. Le nom et l'échange des noms ne se changent qu'à la création.
"""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_DEVICE_CLASS,
    CONF_HIDE_SOURCE,
    CONF_NAME,
    CONF_SEND_STOP_AT_ENDS,
    CONF_SOURCE_ENTITY,
    CONF_SOURCE_ID,
    CONF_SOURCE_SUFFIX,
    CONF_TAKE_OVER,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_HIDE_SOURCE,
    DEFAULT_SEND_STOP_AT_ENDS,
    DEFAULT_SUFFIX,
    DEFAULT_SUFFIX_OTHER,
    DEFAULT_TAKE_OVER,
    DEFAULT_TRAVEL_TIME,
    DEVICE_CLASSES,
    DOMAIN,
)


def _selecteur_temps() -> NumberSelector:
    """Champ « temps en secondes »."""
    return NumberSelector(
        NumberSelectorConfig(
            min=1,
            max=600,
            step=0.1,
            unit_of_measurement="s",
            mode=NumberSelectorMode.BOX,
        )
    )


def _selecteur_type() -> SelectSelector:
    """Liste des classes d'appareil (libellés dans translations/, ceux de Home Assistant)."""
    return SelectSelector(
        SelectSelectorConfig(
            options=DEVICE_CLASSES,
            mode=SelectSelectorMode.DROPDOWN,
            sort=True,
            translation_key="device_class",
        )
    )


def _nom_propose(nom_source: str) -> str:
    """Nom proposé : celui du volet réel sans le suffixe entre crochets (« [overkiz] »)."""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", nom_source).strip() or nom_source


def _suffixe_propose(langue: str) -> str:
    """Suffixe proposé pour l'ouvrant d'origine, dans la langue de l'utilisateur."""
    return DEFAULT_SUFFIX.get(langue.split("-")[0], DEFAULT_SUFFIX_OTHER)


class TimedCoverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Création d'un volet à temps de trajet."""

    VERSION = 1

    def __init__(self) -> None:
        """Mémorise le volet choisi à la première étape."""
        self._source: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Première étape : choisir le volet réel."""
        erreurs: dict[str, str] = {}
        if user_input is not None:
            source = user_input[CONF_SOURCE_ENTITY]
            registre = er.async_get(self.hass)
            entree = registre.async_get(source)
            if entree is None and self.hass.states.get(source) is None:
                erreurs["base"] = "source_introuvable"
            elif entree is not None and entree.platform == DOMAIN:
                erreurs["base"] = "source_deja_chronometree"
            else:
                # L'identifiant interne ne change pas si l'ouvrant est renommé ensuite.
                await self.async_set_unique_id(entree.id if entree is not None else source)
                self._abort_if_unique_id_configured()
                self._source = source
                return await self.async_step_parametres()

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCE_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="cover")
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=erreurs)

    async def async_step_parametres(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Deuxième étape : nom, temps d'ouverture et de fermeture, échange des noms."""
        assert self._source is not None
        erreurs: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_TAKE_OVER] and not slugify(user_input[CONF_SOURCE_SUFFIX]):
                erreurs[CONF_SOURCE_SUFFIX] = "suffixe_invalide"
            else:
                entree = er.async_get(self.hass).async_get(self._source)
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_SOURCE_ENTITY: self._source,
                        CONF_SOURCE_ID: entree.id if entree is not None else None,
                        **user_input,
                    },
                )

        etat = self.hass.states.get(self._source)
        nom_source = etat.name if etat is not None else self._source
        saisi = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=saisi.get(CONF_NAME, _nom_propose(nom_source))
                ): TextSelector(),
                vol.Required(
                    CONF_TRAVEL_TIME_UP, default=saisi.get(CONF_TRAVEL_TIME_UP, DEFAULT_TRAVEL_TIME)
                ): _selecteur_temps(),
                vol.Required(
                    CONF_TRAVEL_TIME_DOWN,
                    default=saisi.get(CONF_TRAVEL_TIME_DOWN, DEFAULT_TRAVEL_TIME),
                ): _selecteur_temps(),
                vol.Required(
                    CONF_SEND_STOP_AT_ENDS, default=DEFAULT_SEND_STOP_AT_ENDS
                ): BooleanSelector(),
                vol.Required(CONF_DEVICE_CLASS, default=DEFAULT_DEVICE_CLASS): _selecteur_type(),
                vol.Required(CONF_HIDE_SOURCE, default=DEFAULT_HIDE_SOURCE): BooleanSelector(),
                vol.Required(
                    CONF_TAKE_OVER, default=saisi.get(CONF_TAKE_OVER, DEFAULT_TAKE_OVER)
                ): BooleanSelector(),
                vol.Required(
                    CONF_SOURCE_SUFFIX,
                    default=saisi.get(
                        CONF_SOURCE_SUFFIX, _suffixe_propose(self.hass.config.language)
                    ),
                ): TextSelector(),
            }
        )
        return self.async_show_form(
            step_id="parametres",
            data_schema=schema,
            errors=erreurs,
            description_placeholders={"source": self._source},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Formulaire d'options (modifier les temps de trajet, etc.)."""
        return TimedCoverOptionsFlow()


class TimedCoverOptionsFlow(OptionsFlow):
    """Modification des réglages d'un volet à temps de trajet."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Formulaire unique d'options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        actuel = {**self.config_entry.data, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TRAVEL_TIME_UP,
                    default=actuel.get(CONF_TRAVEL_TIME_UP, DEFAULT_TRAVEL_TIME),
                ): _selecteur_temps(),
                vol.Required(
                    CONF_TRAVEL_TIME_DOWN,
                    default=actuel.get(CONF_TRAVEL_TIME_DOWN, DEFAULT_TRAVEL_TIME),
                ): _selecteur_temps(),
                vol.Required(
                    CONF_SEND_STOP_AT_ENDS,
                    default=actuel.get(CONF_SEND_STOP_AT_ENDS, DEFAULT_SEND_STOP_AT_ENDS),
                ): BooleanSelector(),
                vol.Required(
                    CONF_DEVICE_CLASS,
                    default=actuel.get(CONF_DEVICE_CLASS, DEFAULT_DEVICE_CLASS),
                ): _selecteur_type(),
                vol.Required(
                    CONF_HIDE_SOURCE,
                    default=actuel.get(CONF_HIDE_SOURCE, DEFAULT_HIDE_SOURCE),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
