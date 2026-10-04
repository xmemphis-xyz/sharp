"""Power and operation modes."""
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)
from .const import MANUAL_SPEEDS, PRESET_MODES, normalize_mode
from .entity import SharpEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities(SharpFan(c, key, "fan") for key in c.data)


class SharpFan(SharpEntity, FanEntity):
    _attr_name = "Air purifier"
    _attr_supported_features = (
        FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        | FanEntityFeature.PRESET_MODE | FanEntityFeature.SET_SPEED
    )
    _attr_preset_modes = PRESET_MODES
    _attr_speed_count = len(MANUAL_SPEEDS)

    @property
    def is_on(self):
        if not self.properties or self.properties.power not in ("on", "off"):
            return None
        return self.properties.power == "on"

    @property
    def preset_mode(self):
        mode = normalize_mode(self.properties.operation_mode) if self.properties else None
        return mode if mode in PRESET_MODES else None

    @property
    def percentage(self):
        if self.is_on is False:
            return 0
        mode = normalize_mode(self.properties.operation_mode) if self.properties else None
        if mode in MANUAL_SPEEDS:
            return ordered_list_item_to_percentage(MANUAL_SPEEDS, mode)
        return None

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        if preset_mode is not None and preset_mode not in PRESET_MODES:
            raise HomeAssistantError("Unsupported Sharp preset mode")
        if percentage is not None and not 0 <= percentage <= 100:
            raise HomeAssistantError("Sharp speed must be between 0 and 100")
        if percentage == 0:
            await self.async_turn_off()
            return
        commands = [("power_on",)]
        if preset_mode is not None:
            commands.append(("set_mode", preset_mode))
        elif percentage is not None:
            commands.append(("set_mode", percentage_to_ordered_list_item(MANUAL_SPEEDS, percentage)))
        await self.coordinator.command_many(self.key, commands)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.command(self.key, "power_off")

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode not in PRESET_MODES:
            raise HomeAssistantError("Unsupported Sharp preset mode")
        await self.coordinator.command(self.key, "set_mode", preset_mode)

    async def async_set_percentage(self, percentage):
        await self.async_turn_on(percentage=percentage)
