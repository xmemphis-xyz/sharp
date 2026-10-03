"""Polling and serialized commands."""
from .api import SharpLifeAirClient

import asyncio
import logging
from datetime import timedelta
from aiosharp_cocoro_air import SharpAuthError, SharpApiError, SharpConnectionError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed


class SharpCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, logging.getLogger(__name__), name="Sharp Life AIR",
                         config_entry=entry, update_interval=timedelta(seconds=60))
        # The API relies on cookies; isolate these from HA's shared session.
        self.client = SharpLifeAirClient(entry.data["email"], entry.data["password"])
        self.lock = asyncio.Lock()
        self.authenticated = False

    async def _async_update_data(self):
        async with self.lock:
            try:
                async with asyncio.timeout(90):
                    if not self.authenticated:
                        await self.client.authenticate()
                        self.authenticated = True
                    devices = await self.client.get_devices()
                    return {(d.box_id, d.device_id): d for d in devices}
            except SharpAuthError as err:
                self.authenticated = False
                raise ConfigEntryAuthFailed("Sharp authentication expired") from err
            except (SharpApiError, SharpConnectionError, TimeoutError) as err:
                raise UpdateFailed("Unable to retrieve Sharp devices") from err

    async def command(self, key, method, *args):
        async with self.lock:
            device = self.data.get(key)
            if device is None:
                raise HomeAssistantError("Sharp device is unavailable")
            try:
                async with asyncio.timeout(60):
                    await getattr(self.client, method)(device, *args)
            except SharpAuthError as err:
                self.authenticated = False
                raise ConfigEntryAuthFailed("Sharp authentication expired") from err
            except (SharpApiError, SharpConnectionError, TimeoutError) as err:
                raise HomeAssistantError("Sharp command failed") from err
        await self.async_request_refresh()
