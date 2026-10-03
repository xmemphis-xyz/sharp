"""Decoded readings and raw diagnostic values."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfPower, UnitOfEnergy
from homeassistant.helpers.entity import EntityCategory
from .entity import SharpEntity

READINGS = {
    "temperature_c": ("Temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT),
    "humidity_pct": ("Humidity", "%", SensorDeviceClass.HUMIDITY, SensorStateClass.MEASUREMENT),
    "power_watts": ("Power", UnitOfPower.WATT, SensorDeviceClass.POWER, SensorStateClass.MEASUREMENT),
    # No total_increasing until the device counter's reset behavior is confirmed.
    "energy_wh": ("Energy", UnitOfEnergy.WATT_HOUR, SensorDeviceClass.ENERGY, None),
    "airflow": ("Airflow", None, None, None),
    "cleaning_mode": ("Cleaning mode", None, None, None),
    "operation_mode": ("Operation mode", None, None, None),
}
RAW = ["pci_sensor", "filter_usage", "dust", "smell", "humidity_filter", "light_sensor"]


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    async_add_entities(SharpSensor(c, key, field) for key in c.data for field in [*READINGS, *RAW])


class SharpSensor(SharpEntity, SensorEntity):
    def __init__(self, coordinator, key, field):
        super().__init__(coordinator, key, field)
        self.field = field
        if field in READINGS:
            name, unit, device_class, state_class = READINGS[field]
            self._attr_name = name
            self._attr_native_unit_of_measurement = unit
            self._attr_device_class = device_class
            self._attr_state_class = state_class
        else:
            self._attr_name = field.replace("_", " ").capitalize() + " raw"
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        return getattr(self.properties, self.field, None)
