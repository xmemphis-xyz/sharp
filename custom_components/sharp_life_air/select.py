"""Explicit operation mode control on the device page."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .const import MODES, normalize_mode
from .entity import SharpEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(SharpMode(coordinator, key, "mode") for key in coordinator.data)


class SharpMode(SharpEntity, SelectEntity):
    _attr_name = "Operation mode"
    _attr_icon = "mdi:air-purifier"
    _attr_options = MODES

    @property
    def current_option(self):
        return normalize_mode(self.properties.operation_mode) if self.properties else None

    async def async_select_option(self, option):
        if option not in MODES:
            raise HomeAssistantError("Unsupported Sharp mode")
        await self.coordinator.command(self.key, "set_mode", option)
