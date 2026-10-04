"""Configure Sharp Life AIR."""
from .api import SharpLifeAirClient

import asyncio
import voluptuous as vol
from aiosharp_cocoro_air import SharpAuthError, SharpApiError, SharpConnectionError
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from .const import DOMAIN, CONF_TERMINAL_APP_ID


class SharpConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input[CONF_EMAIL] = user_input[CONF_EMAIL].strip()
            try:
                async with asyncio.timeout(90):
                    async with SharpLifeAirClient(user_input[CONF_EMAIL], user_input[CONF_PASSWORD]) as client:
                        await client.authenticate()
                        devices = await client.get_devices()
                        account_id = client.user_id or user_input[CONF_EMAIL].casefold()
                        terminal_app_id = client.terminal_app_id
                if not devices:
                    errors["base"] = "no_devices"
                else:
                    await self.async_set_unique_id(str(account_id))
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title="Sharp Life AIR", data={
                        **user_input, CONF_TERMINAL_APP_ID: terminal_app_id,
                    })
            except SharpAuthError:
                errors["base"] = "invalid_auth"
            except (SharpApiError, SharpConnectionError, TimeoutError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="user", data_schema=vol.Schema({
            vol.Required(CONF_EMAIL): str,
            vol.Required(CONF_PASSWORD): str,
        }), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                async with asyncio.timeout(90):
                    async with SharpLifeAirClient(entry.data[CONF_EMAIL], user_input[CONF_PASSWORD],
                            terminal_app_id=entry.data.get(CONF_TERMINAL_APP_ID)) as client:
                        await client.authenticate()
                        account_id = client.user_id or entry.data[CONF_EMAIL].casefold()
                        terminal_app_id = client.terminal_app_id
                await self.async_set_unique_id(str(account_id))
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data_updates={
                    **user_input, CONF_TERMINAL_APP_ID: terminal_app_id,
                })
            except SharpAuthError:
                errors["base"] = "invalid_auth"
            except (SharpApiError, SharpConnectionError, TimeoutError):
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({
            vol.Required(CONF_PASSWORD): str,
        }), errors=errors)
