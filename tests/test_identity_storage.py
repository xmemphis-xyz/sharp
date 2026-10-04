"""Test integration identity storage with small HA interface doubles.

These tests exercise the integration's flow/coordinator code, not HA runtime.
"""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


class CoordinatorDouble:
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass


class FlowDouble:
    def __init_subclass__(cls, **kwargs):
        pass


def load_integration():
    root = Path(__file__).parents[1]/"custom_components/sharp_life_air"
    package_name = "identity_test_integration"
    package = ModuleType(package_name)
    package.__path__ = [str(root)]
    ha = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.ConfigFlow = FlowDouble
    ha.config_entries = config_entries
    const = ModuleType("homeassistant.const")
    const.CONF_EMAIL = "email"
    const.CONF_PASSWORD = "password"
    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    exceptions.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    update = ModuleType("homeassistant.helpers.update_coordinator")
    update.DataUpdateCoordinator = CoordinatorDouble
    update.UpdateFailed = type("UpdateFailed", (Exception,), {})
    event = ModuleType("homeassistant.helpers.event")
    event.async_call_later = Mock()
    vol = ModuleType("voluptuous")
    vol.Schema = dict
    vol.Required = lambda key: key
    modules = {package_name:package, "homeassistant":ha,
               "homeassistant.config_entries":config_entries, "homeassistant.const":const,
               "homeassistant.exceptions":exceptions,
               "homeassistant.helpers":ModuleType("homeassistant.helpers"),
               "homeassistant.helpers.update_coordinator":update,
               "homeassistant.helpers.event":event, "voluptuous":vol}
    with patch.dict(sys.modules, modules):
        loaded = []
        for name in ("const", "api", "coordinator", "config_flow"):
            qualified = f"{package_name}.{name}"
            spec = importlib.util.spec_from_file_location(qualified, root/f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[qualified] = module
            spec.loader.exec_module(module)
            loaded.append(module)
    return loaded[-2:]


coordinator_module, flow_module = load_integration()


def client_double():
    client = SimpleNamespace(terminal_app_id="saved-terminal", user_id="fake-account",
                             authenticate=AsyncMock(), get_devices=AsyncMock(return_value=[]))
    context = Mock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    return client, context


class IdentityStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_allocated_identity_survives_later_registration_failure(self):
        entry = SimpleNamespace(data={"email":"test@example.invalid", "password":"fake"},
                                async_on_unload=Mock())
        update = Mock()
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
        client, _ = client_double()
        client.authenticate.side_effect = coordinator_module.SharpApiError("setting/terminal: HTTP 503")
        with patch.object(coordinator_module, "SharpLifeAirClient", return_value=client):
            coordinator = coordinator_module.SharpCoordinator(hass, entry)
            with self.assertRaises(coordinator_module.UpdateFailed):
                await coordinator._async_update_data()
        self.assertFalse(coordinator.authenticated)
        update.assert_called_once_with(entry, data={"email":"test@example.invalid", "password":"fake",
                                                   "terminal_app_id":"saved-terminal"})

    async def test_legacy_entry_is_upgraded_once_and_restart_reuses_identity(self):
        entry = SimpleNamespace(data={"email":"test@example.invalid", "password":"fake"},
                                async_on_unload=Mock())
        def update_entry(target, *, data):
            target.data = data
        update = Mock(side_effect=update_entry)
        hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update))
        client, _ = client_double()
        with patch.object(coordinator_module, "SharpLifeAirClient", return_value=client) as factory:
            coordinator = coordinator_module.SharpCoordinator(hass, entry)
            factory.assert_called_once_with("test@example.invalid", "fake", terminal_app_id=None)
            await coordinator._async_update_data()
            await coordinator._async_update_data()
            update.assert_called_once()
            self.assertEqual(entry.data, {"email":"test@example.invalid", "password":"fake",
                                          "terminal_app_id":"saved-terminal"})
            factory.reset_mock()
            restarted = coordinator_module.SharpCoordinator(hass, entry)
            factory.assert_called_once_with("test@example.invalid", "fake", terminal_app_id="saved-terminal")
            await restarted._async_update_data()
            update.assert_called_once()

    async def test_new_config_flow_stores_validated_client_identity(self):
        client, context = client_double()
        client.get_devices.return_value = [object()]
        flow = flow_module.SharpConfigFlow()
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        flow.async_create_entry = Mock(side_effect=lambda **kwargs: kwargs)
        with patch.object(flow_module, "SharpLifeAirClient", return_value=context):
            result = await flow.async_step_user({"email":"test@example.invalid", "password":"fake"})
        self.assertEqual(result["data"]["terminal_app_id"], "saved-terminal")
        flow.async_set_unique_id.assert_awaited_once_with("fake-account")

    async def test_reauth_reuses_and_preserves_identity_with_updated_password(self):
        entry = SimpleNamespace(data={"email":"test@example.invalid", "password":"old",
                                      "terminal_app_id":"saved-terminal"})
        client, context = client_double()
        flow = flow_module.SharpConfigFlow()
        flow._get_reauth_entry = Mock(return_value=entry)
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_mismatch = Mock()
        flow.async_update_reload_and_abort = Mock()
        with patch.object(flow_module, "SharpLifeAirClient", return_value=context) as factory:
            await flow.async_step_reauth_confirm({"password":"new"})
        factory.assert_called_once_with("test@example.invalid", "new", terminal_app_id="saved-terminal")
        flow.async_update_reload_and_abort.assert_called_once_with(entry, data_updates={
            "password":"new", "terminal_app_id":"saved-terminal",
        })
