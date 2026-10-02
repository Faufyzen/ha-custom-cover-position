"""Constantes de l'intégration « Volets à temps de trajet »."""

DOMAIN = "timed_cover"

# Clés de configuration (formulaire de création et d'options).
CONF_SOURCE_ENTITY = "source_entity"
CONF_NAME = "name"
CONF_TRAVEL_TIME_UP = "travel_time_up"
CONF_TRAVEL_TIME_DOWN = "travel_time_down"
CONF_SEND_STOP_AT_ENDS = "send_stop_at_ends"
CONF_DEVICE_CLASS = "device_class"
CONF_HIDE_SOURCE = "hide_source"

# Valeurs proposées par défaut.
DEFAULT_TRAVEL_TIME = 30.0
DEFAULT_SEND_STOP_AT_ENDS = False
DEFAULT_DEVICE_CLASS = "shutter"
DEFAULT_HIDE_SOURCE = True

# Types de volets proposés (classes d'appareil de Home Assistant).
DEVICE_CLASSES = ["shutter", "blind", "awning", "curtain", "shade", "window"]

# Attributs exposés par l'entité.
ATTR_SOURCE_ENTITY = "source_entity"
ATTR_TRAVEL_TIME_UP = "travel_time_up"
ATTR_TRAVEL_TIME_DOWN = "travel_time_down"
ATTR_TARGET_POSITION = "target_position"

SERVICE_SET_KNOWN_POSITION = "set_known_position"
