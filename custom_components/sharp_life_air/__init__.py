"""Sharp Life AIR cloud integration."""
from homeassistant.const import Platform
from .coordinator import SharpCoordinator

PLATFORMS = [Platform.FAN, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.BINARY_SENSOR]


async def async_setup_entry(hass, entry):
    coordinator = SharpCoordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await coordinator.client.close()
        raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.close()
        return True
    return False
