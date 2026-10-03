"""Constantes de l'intégration « Custom Cover Position » (timed_cover)."""

DOMAIN = "timed_cover"

# Clés de configuration (formulaire de création et d'options).
CONF_SOURCE_ENTITY = "source_entity"
CONF_NAME = "name"
CONF_TRAVEL_TIME_UP = "travel_time_up"
CONF_TRAVEL_TIME_DOWN = "travel_time_down"
CONF_SEND_STOP_AT_ENDS = "send_stop_at_ends"
CONF_DEVICE_CLASS = "device_class"
CONF_HIDE_SOURCE = "hide_source"
CONF_SOURCE_ID = "source_id"  # identifiant interne de l'ouvrant d'origine (survit à un renommage)
CONF_TAKE_OVER = "take_over"  # reprendre le nom et l'identifiant de l'ouvrant d'origine
CONF_SOURCE_SUFFIX = "source_suffix"  # suffixe donné à l'ouvrant d'origine une fois renommé
CONF_PRESETS = "presets"  # positions prédéfinies : liste de {name, position, icon}
CONF_PRESET_NAME = "name"
CONF_PRESET_POSITION = "position"
CONF_PRESET_ICON = "icon"
CONF_FAVORITES_APPLIED = "favorites_applied"  # favoris de la fenêtre de l'ouvrant posés par nous
SECTION_POSITIONS = "positions"  # bloc du formulaire qui contient la liste des positions
MAX_PRESETS = 8  # au plus 8 positions : au-delà, la fenêtre de l'ouvrant devient illisible
CONF_DISABLE_OTHERS = "disable_other_entities"  # désactiver les autres entités de l'appareil d'origine
CONF_DISABLED_BY_US = "disabled_entities"  # identifiants (registre) des entités désactivées par nous
CONF_RESTORE = "restore"  # ce qu'il faut remettre en état à la suppression (voir __init__.py)

# Valeurs proposées par défaut.
DEFAULT_TRAVEL_TIME = 30.0
DEFAULT_SEND_STOP_AT_ENDS = False
DEFAULT_DEVICE_CLASS = "shutter"
DEFAULT_HIDE_SOURCE = True
DEFAULT_TAKE_OVER = True
DEFAULT_DISABLE_OTHERS = False  # prudent : elle désactive aussi les capteurs (batterie, puissance…)
DEFAULT_SUFFIX = {"fr": "origine"}  # langue -> suffixe proposé
DEFAULT_SUFFIX_OTHER = "source"

# Classes d'appareil d'un ouvrant (toutes celles de Home Assistant).
DEVICE_CLASSES = [
    "awning",
    "blind",
    "curtain",
    "damper",
    "door",
    "garage",
    "gate",
    "shade",
    "shutter",
    "window",
]

# Attributs exposés par l'entité.
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_TRAVEL_TIME_UP = "travel_time_up"
ATTR_TRAVEL_TIME_DOWN = "travel_time_down"
ATTR_TARGET_POSITION = "target_position"

SERVICE_SET_KNOWN_POSITION = "set_known_position"
