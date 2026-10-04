"""Constants for Sharp Life AIR."""
DOMAIN = "sharp_life_air"
CONF_TERMINAL_APP_ID = "terminal_app_id"
MODES = ["auto", "night", "pollen", "silent", "medium", "high", "ai_auto", "realize"]
MANUAL_SPEEDS = ["silent", "medium", "high"]
PRESET_MODES = [mode for mode in MODES if mode not in MANUAL_SPEEDS]


def normalize_mode(value):
    """Use the same API mode names for the fan and select entities."""
    if not value:
        return None
    mode = value.lower().replace(" ", "_")
    return mode if mode in MODES else None
