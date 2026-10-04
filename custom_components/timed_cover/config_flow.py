"""Étapes de configuration d'un volet à temps de trajet, ou d'un groupe de volets.

Création : un menu (entité ou groupe), puis
  - pour une entité, deux étapes : 1. choisir l'ouvrant réel à enrober (par exemple le volet
    Overkiz) ; 2. donner un nom, les temps d'ouverture et de fermeture, et l'échange des noms ;
  - pour un groupe, une étape : un nom et les volets (entités de cette intégration) à réunir.
Options (bouton « Configurer » de l'entrée) : temps, ordre d'arrêt aux extrémités, classe d'appareil,
masquage de l'ouvrant d'origine ; pour un groupe, la liste de ses volets. Le nom et l'échange des
noms ne se changent qu'à la création.
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
from homeassistant.data_entry_flow import section
from homeassistant.helpers import entity_registry as er
from homeassistant.util import slugify
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    ObjectSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from . import groupe
from .const import (
    CONF_DEVICE_CLASS,
    CONF_DISABLE_OTHERS,
    CONF_HIDE_SOURCE,
    CONF_KIND,
    CONF_MEMBERS,
    CONF_NAME,
    CONF_PRESET_ICON,
    CONF_PRESET_NAME,
    CONF_PRESET_POSITION,
    CONF_PRESETS,
    CONF_SEND_STOP_AT_ENDS,
    CONF_SOURCE_ENTITY,
    CONF_SOURCE_ID,
    CONF_SOURCE_SUFFIX,
    CONF_TAKE_OVER,
    CONF_TRAVEL_TIME_DOWN,
    CONF_TRAVEL_TIME_UP,
    DEFAULT_DEVICE_CLASS,
    DEFAULT_DISABLE_OTHERS,
    DEFAULT_HIDE_SOURCE,
    DEFAULT_SEND_STOP_AT_ENDS,
    DEFAULT_SUFFIX,
    DEFAULT_TAKE_OVER,
    DEFAULT_TRAVEL_TIME,
    DEVICE_CLASSES,
    DOMAIN,
    KIND_GROUP,
    MAX_PRESETS,
    SECTION_POSITIONS,
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


def _selecteur_positions() -> ObjectSelector:
    """Liste de positions prédéfinies : une ligne par position, avec « + » pour en ajouter."""
    return ObjectSelector(
        {
            "multiple": True,
            "label_field": CONF_PRESET_NAME,
            "description_field": CONF_PRESET_POSITION,
            "translation_key": "presets",
            "fields": {
                CONF_PRESET_NAME: {"required": True, "selector": {"text": {}}},
                CONF_PRESET_POSITION: {
                    "required": True,
                    "selector": {
                        "number": {"min": 0, "max": 100, "step": 1, "unit_of_measurement": "%"}
                    },
                },
                CONF_PRESET_ICON: {"required": False, "selector": {"icon": {}}},
            },
        }
    )


def _bloc_positions(par_defaut: list[dict[str, Any]], ouvert: bool) -> section:
    """Bloc « Positions prédéfinies » du formulaire : un titre et une explication au-dessus de la liste.

    Il est replié tant qu'aucune position n'existe (la plupart des ouvrants n'en ont pas), et
    ouvert dès qu'il y en a, ou qu'une erreur l'exige.
    """
    return section(
        vol.Schema(
            {vol.Optional(CONF_PRESETS, default=par_defaut): _selecteur_positions()}
        ),
        {"collapsed": not ouvert},
    )


def _positions_du_bloc(user_input: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Sort la liste du bloc (le bloc imbrique les données sous la clé SECTION_POSITIONS)."""
    return (user_input.get(SECTION_POSITIONS) or {}).get(CONF_PRESETS)


def _sans_bloc(user_input: dict[str, Any], positions: list[dict[str, Any]]) -> dict[str, Any]:
    """Données à enregistrer : le bloc est remplacé par la liste de positions, à plat."""
    donnees = {k: v for k, v in user_input.items() if k != SECTION_POSITIONS}
    donnees[CONF_PRESETS] = positions
    return donnees


def _valider_positions(brutes: list[dict[str, Any]] | None) -> tuple[list[dict[str, Any]], str | None]:
    """Nettoie la liste des positions ; renvoie (liste, clé d'erreur ou None)."""
    propres: list[dict[str, Any]] = []
    vus: set[str] = set()
    if len(brutes or []) > MAX_PRESETS:
        return [], "trop_de_positions"
    for ligne in brutes or []:
        nom = str(ligne.get(CONF_PRESET_NAME, "")).strip()
        try:
            position = round(float(ligne.get(CONF_PRESET_POSITION)))
        except (TypeError, ValueError):
            return [], "positions_invalides"
        if not slugify(nom) or not 0 <= position <= 100:
            return [], "positions_invalides"
        if slugify(nom) in vus:
            return [], "noms_en_double"
        vus.add(slugify(nom))
        nettoyee = {CONF_PRESET_NAME: nom, CONF_PRESET_POSITION: position}
        if ligne.get(CONF_PRESET_ICON):
            nettoyee[CONF_PRESET_ICON] = str(ligne[CONF_PRESET_ICON])
        propres.append(nettoyee)
    return propres, None


def _nom_propose(nom_source: str) -> str:
    """Nom proposé : celui du volet réel sans le suffixe entre crochets (« [overkiz] »)."""
    return re.sub(r"\s*\[[^\]]*\]\s*$", "", nom_source).strip() or nom_source


def _selecteur_volets(hass: Any) -> EntitySelector:
    """Choix des volets d'un groupe : les entités de cette intégration, sauf les groupes.

    Un groupe de groupes n'est pas prévu (un groupe commande des volets qui estiment chacun
    leur position) : les entités des groupes sont donc retirées de la liste.
    """
    registre = er.async_get(hass)
    groupes = [
        i
        for g in groupe.entrees_des_groupes(hass)
        if (i := registre.async_get_entity_id("cover", DOMAIN, g.entry_id)) is not None
    ]
    return EntitySelector(
        EntitySelectorConfig(
            domain="cover", integration=DOMAIN, multiple=True, exclude_entities=groupes
        )
    )


def _valider_volets(hass: Any, entites: list[str]) -> tuple[list[str], str | None]:
    """Transforme les entités choisies en identifiants d'entrées ; renvoie (liste, clé d'erreur)."""
    registre = er.async_get(hass)
    entrees: list[str] = []
    for identifiant in entites:
        entree = registre.async_get(identifiant)
        configuration = (
            hass.config_entries.async_get_entry(entree.config_entry_id)
            if entree is not None and entree.config_entry_id
            else None
        )
        if configuration is None or configuration.domain != DOMAIN or groupe.est_groupe(configuration):
            return [], "volet_invalide"
        if configuration.entry_id not in entrees:
            entrees.append(configuration.entry_id)
    if len(entrees) < 2:
        return [], "groupe_trop_petit"
    return entrees, None


class TimedCoverConfigFlow(ConfigFlow, domain=DOMAIN):
    """Création d'un volet à temps de trajet."""

    VERSION = 1

    def __init__(self) -> None:
        """Mémorise le volet choisi à la première étape."""
        self._source: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu de départ : une entité personnalisée, ou un groupe de volets."""
        return self.async_show_menu(step_id="user", menu_options=["entite", "groupe"])

    async def async_step_groupe(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Création d'un groupe : un nom et les volets à réunir."""
        erreurs: dict[str, str] = {}
        if user_input is not None:
            volets, erreur = _valider_volets(self.hass, user_input[CONF_MEMBERS])
            if not slugify(user_input[CONF_NAME]):
                erreurs[CONF_NAME] = "nom_invalide"
            elif erreur:
                erreurs[CONF_MEMBERS] = erreur
            else:
                nom = user_input[CONF_NAME].strip()
                return self.async_create_entry(
                    title=nom,
                    data={CONF_KIND: KIND_GROUP, CONF_NAME: nom, CONF_MEMBERS: volets},
                )
        saisi = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, **({"default": saisi[CONF_NAME]} if CONF_NAME in saisi else {})): TextSelector(),
                vol.Required(
                    CONF_MEMBERS, **({"default": saisi[CONF_MEMBERS]} if CONF_MEMBERS in saisi else {})
                ): _selecteur_volets(self.hass),
            }
        )
        return self.async_show_form(step_id="groupe", data_schema=schema, errors=erreurs)

    async def async_step_entite(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Première étape d'une entité : choisir le volet réel."""
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
        return self.async_show_form(step_id="entite", data_schema=schema, errors=erreurs)

    async def async_step_parametres(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Deuxième étape : nom, temps d'ouverture et de fermeture, échange des noms."""
        assert self._source is not None
        erreurs: dict[str, str] = {}
        if user_input is not None:
            positions, erreur_positions = _valider_positions(_positions_du_bloc(user_input))
            if user_input[CONF_TAKE_OVER] and not slugify(user_input[CONF_SOURCE_SUFFIX]):
                erreurs[CONF_SOURCE_SUFFIX] = "suffixe_invalide"
            elif erreur_positions:
                erreurs[SECTION_POSITIONS] = erreur_positions
            else:
                entree = er.async_get(self.hass).async_get(self._source)
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_SOURCE_ENTITY: self._source,
                        CONF_SOURCE_ID: entree.id if entree is not None else None,
                        **_sans_bloc(user_input, positions),
                    },
                )

        etat = self.hass.states.get(self._source)
        nom_source = etat.name if etat is not None else self._source
        saisi = user_input or {}
        positions_saisies = (saisi.get(SECTION_POSITIONS) or {}).get(CONF_PRESETS, [])
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
                    CONF_DISABLE_OTHERS, default=DEFAULT_DISABLE_OTHERS
                ): BooleanSelector(),
                vol.Optional(
                    SECTION_POSITIONS, default={CONF_PRESETS: positions_saisies}
                ): _bloc_positions(
                    positions_saisies, bool(positions_saisies) or SECTION_POSITIONS in erreurs
                ),
                vol.Required(
                    CONF_TAKE_OVER, default=saisi.get(CONF_TAKE_OVER, DEFAULT_TAKE_OVER)
                ): BooleanSelector(),
                vol.Required(
                    CONF_SOURCE_SUFFIX,
                    default=saisi.get(
                        CONF_SOURCE_SUFFIX, DEFAULT_SUFFIX
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

    async def async_step_groupe(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Options d'un groupe : la liste de ses volets (le nom ne se change qu'à la création)."""
        erreurs: dict[str, str] = {}
        if user_input is not None:
            volets, erreur = _valider_volets(self.hass, user_input[CONF_MEMBERS])
            if erreur:
                erreurs[CONF_MEMBERS] = erreur
            else:
                return self.async_create_entry(data={CONF_MEMBERS: volets})
        actuels = (
            user_input[CONF_MEMBERS]
            if user_input is not None
            else groupe.ids_membres(self.hass, self.config_entry)
        )
        schema = vol.Schema(
            {vol.Required(CONF_MEMBERS, default=actuels): _selecteur_volets(self.hass)}
        )
        return self.async_show_form(step_id="groupe", data_schema=schema, errors=erreurs)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Formulaire unique d'options."""
        if groupe.est_groupe(self.config_entry):
            return await self.async_step_groupe()
        erreurs: dict[str, str] = {}
        if user_input is not None:
            positions, erreur_positions = _valider_positions(_positions_du_bloc(user_input))
            if erreur_positions:
                erreurs[SECTION_POSITIONS] = erreur_positions
            else:
                return self.async_create_entry(data=_sans_bloc(user_input, positions))

        actuel = {**self.config_entry.data, **self.config_entry.options}
        positions_actuelles = (
            _positions_du_bloc(user_input) if user_input is not None else actuel.get(CONF_PRESETS)
        ) or []
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
                vol.Required(
                    CONF_DISABLE_OTHERS,
                    default=actuel.get(CONF_DISABLE_OTHERS, DEFAULT_DISABLE_OTHERS),
                ): BooleanSelector(),
                # La valeur par défaut du bloc doit porter la liste : l'interface n'applique pas
                # les valeurs par défaut des champs situés à l'intérieur d'un bloc.
                vol.Optional(
                    SECTION_POSITIONS, default={CONF_PRESETS: positions_actuelles}
                ): _bloc_positions(
                    positions_actuelles, bool(positions_actuelles) or SECTION_POSITIONS in erreurs
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=erreurs)
