"""Polling and serialized commands."""
from .api import SharpLifeAirClient
from .const import CONF_TERMINAL_APP_ID

import asyncio
import logging
from datetime import timedelta
from aiosharp_cocoro_air import SharpAuthError, SharpApiError, SharpConnectionError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_call_later

_LOGGER = logging.getLogger(__name__)


class SharpCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, logging.getLogger(__name__), name="Sharp Life AIR",
                         config_entry=entry, update_interval=timedelta(seconds=60))
        # The API relies on cookies; isolate these from HA's shared session.
        self.entry = entry
        self.client = SharpLifeAirClient(entry.data["email"], entry.data["password"],
                                        terminal_app_id=entry.data.get(CONF_TERMINAL_APP_ID))
        self.lock = asyncio.Lock()
        self.authenticated = False
        self._cancel_refresh = None
        entry.async_on_unload(self._cancel_followup_refresh)

    def _cancel_followup_refresh(self):
        if self._cancel_refresh is not None:
            self._cancel_refresh()
            self._cancel_refresh = None

    async def _followup_refresh(self, _now):
        self._cancel_refresh = None
        await self.async_request_refresh()

    def _schedule_refresh(self, delay=5):
        self._cancel_followup_refresh()
        self._cancel_refresh = async_call_later(self.hass, delay, self._followup_refresh)

    async def _async_update_data(self):
        async with self.lock:
            try:
                async with asyncio.timeout(90):
                    if not self.authenticated:
                        try:
                            await self.client.authenticate()
                        finally:
                            # Retain an allocated identity even when a later
                            # login/registration request fails. HA setup retries
                            # construct a new coordinator and must not allocate
                            # another terminal on every failed attempt.
                            identity = self.client.terminal_app_id
                            if identity and self.entry.data.get(CONF_TERMINAL_APP_ID) != identity:
                                self.hass.config_entries.async_update_entry(self.entry, data={
                                    **self.entry.data, CONF_TERMINAL_APP_ID: identity,
                                })
                        self.authenticated = True
                    devices = await self.client.get_devices()
                    return {(d.box_id, d.device_id): d for d in devices}
            except SharpAuthError as err:
                self.authenticated = False
                raise ConfigEntryAuthFailed("Sharp authentication expired") from err
            except SharpApiError as err:
                raise UpdateFailed(f"Unable to retrieve Sharp devices: {err}") from err
            except (SharpConnectionError, TimeoutError) as err:
                raise UpdateFailed("Unable to retrieve Sharp devices: connection or timeout") from err

    async def command(self, key, method, *args):
        await self.command_many(key, [(method, *args)])

    async def command_many(self, key, commands):
        if any(command[0] not in {"power_on", "power_off", "set_mode", "set_humidify"}
               for command in commands):
            raise HomeAssistantError("Unsupported Sharp command")
        async with self.lock:
            device = self.data.get(key)
            if device is None:
                raise HomeAssistantError("Sharp device is unavailable")
            try:
                async with asyncio.timeout(60):
                    for method, *args in commands:
                        await getattr(self.client, method)(device, *args)
            except SharpAuthError as err:
                self.authenticated = False
                raise ConfigEntryAuthFailed("Sharp authentication expired") from err
            except (SharpApiError, SharpConnectionError, TimeoutError) as err:
                detail = str(err) if isinstance(err, SharpApiError) else (
                    "Timed out waiting for Sharp; command outcome is unknown"
                    if isinstance(err, TimeoutError) else "Sharp connection failed"
                )
                _LOGGER.warning("Sharp command %s failed: %s", method, detail)
                # The command may have reached the device even if confirmation
                # failed. Refresh state without repeating the write.
                self._schedule_refresh(1)
                raise HomeAssistantError(f"Sharp command failed: {detail}") from err
        self._schedule_refresh()
        await self.async_request_refresh()
