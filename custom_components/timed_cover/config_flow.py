"""Étapes de configuration d'un volet à temps de trajet.

Création : deux étapes.
  1. choisir le volet réel à enrober (par exemple le volet Overkiz) ;
  2. donner un nom et les temps de montée et de descente.
Options (bouton « Configurer » de l'entrée) : temps, ordre d'arrêt aux extrémités, type de volet.
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
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_HIDE_SOURCE,
    DEFAULT_SEND_STOP_AT_ENDS,
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
    """Liste des types de volets (libellés en français dans translations/fr.json)."""
    return SelectSelector(
        SelectSelectorConfig(
            options=DEVICE_CLASSES,
            mode=SelectSelectorMode.DROPDOWN,
            translation_key="device_class",
        )
    )


def _nom_propose(nom_source: str) -> str:
    """Nom proposé : celui du volet réel sans le suffixe entre crochets (« [overkiz] »)."""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", nom_source).strip() or nom_source


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
                await self.async_set_unique_id(source)
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
        """Deuxième étape : nom et temps de trajet."""
        assert self._source is not None
        if user_input is not None:
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_SOURCE_ENTITY: self._source, **user_input},
            )

        etat = self.hass.states.get(self._source)
        nom_source = etat.name if etat is not None else self._source
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=_nom_propose(nom_source)): TextSelector(),
                vol.Required(CONF_TRAVEL_TIME_UP, default=DEFAULT_TRAVEL_TIME): _selecteur_temps(),
                vol.Required(CONF_TRAVEL_TIME_DOWN, default=DEFAULT_TRAVEL_TIME): _selecteur_temps(),
                vol.Required(
                    CONF_SEND_STOP_AT_ENDS, default=DEFAULT_SEND_STOP_AT_ENDS
                ): BooleanSelector(),
                vol.Required(CONF_DEVICE_CLASS, default=DEFAULT_DEVICE_CLASS): _selecteur_type(),
                vol.Required(CONF_HIDE_SOURCE, default=DEFAULT_HIDE_SOURCE): BooleanSelector(),
            }
        )
        return self.async_show_form(
            step_id="parametres",
            data_schema=schema,
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
