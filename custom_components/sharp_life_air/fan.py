"""Power and operation modes."""
from homeassistant.components.fan import FanEntity, FanEntityFeature
from .const import MODES
from .entity import SharpEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities(SharpFan(c, key, "fan") for key in c.data)


class SharpFan(SharpEntity, FanEntity):
    _attr_name = "Air purifier"
    _attr_supported_features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF | FanEntityFeature.PRESET_MODE
    _attr_preset_modes = MODES

    @property
    def is_on(self):
        return self.properties.power == "on" if self.properties and self.properties.power is not None else None

    @property
    def preset_mode(self):
        if not self.properties or not self.properties.operation_mode:
            return None
        value = self.properties.operation_mode.lower().replace(" ", "_")
        return value if value in MODES else None

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        await self.coordinator.command(self.key, "power_on")
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.command(self.key, "power_off")

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode not in MODES:
            raise ValueError("Unsupported Sharp mode")
        await self.coordinator.command(self.key, "set_mode", preset_mode)
