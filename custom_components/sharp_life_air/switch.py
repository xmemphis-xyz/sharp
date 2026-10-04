"""Humidification control."""
from homeassistant.components.switch import SwitchEntity
from .entity import SharpEntity


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities(SharpHumidify(c, key, "humidify") for key in c.data
                       if c.data[key].properties.humidify is not None
                       or (c.data[key].model or "").upper().replace("-", "").startswith("KI"))


class SharpHumidify(SharpEntity, SwitchEntity):
    _attr_name = "Humidification"
    _attr_icon = "mdi:air-humidifier"

    @property
    def is_on(self):
        return self.properties.humidify if self.properties else None

    async def async_turn_on(self, **kwargs):
        await self.coordinator.command(self.key, "set_humidify", True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.command(self.key, "set_humidify", False)
