"""Common Sharp entity."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN


class SharpEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, suffix):
        super().__init__(coordinator)
        self.key = key
        device = coordinator.data[key]
        self._attr_unique_id = f"{key[0]}_{key[1]}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{key[0]}_{key[1]}")},
            name=device.name, manufacturer="Sharp", model=device.model,
            sw_version=device.properties.firmware,
        )

    @property
    def available(self):
        return super().available and self.key in self.coordinator.data

    @property
    def properties(self):
        device = self.coordinator.data.get(self.key)
        return device.properties if device else None
