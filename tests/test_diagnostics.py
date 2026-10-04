"""Protocol capability and freshness diagnostics must omit private data."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

spec = importlib.util.spec_from_file_location(
    "sharp_diagnostics", Path(__file__).parents[1]/"custom_components/sharp_life_air/diagnostics.py"
)
diagnostics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostics)


class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_download_exposes_capabilities_and_freshness_without_identifiers(self):
        device = SimpleNamespace(box_id="private-box", device_id=123,
            echonet_node="private-node", echonet_object="private-object",
            properties=SimpleNamespace(humidity_pct=50, temperature_c=23, power_watts=9))
        identity = {"deviceId":123, "echonetNode":"private-node", "echonetObject":"private-object",
                    "propertyUpdatedAt":"2026-10-04T06:00:00", "serialNumber":"private-serial"}
        client = SimpleNamespace(_hms_request=AsyncMock(side_effect=[
            {"box": [{"boxId":"private-box", "pairingFlag":True, "maxFlag":False,
                "pairedTerminalNum":2, "timezone":"Europe/Warsaw", "terminalAppInfo":[
                    {"terminalAppId":"private-current", "appName":"spremote_a_eu:1:1.0.4"},
                    {"terminalAppId":"private-other", "name":"private-phone"}]}]},
            {"deviceProperty": {**identity, "property": [
                {"statusCode":"80", "valueType":"valueSingle", "set":True, "get":True},
                {"statusCode":"F3", "valueType":"valueBinary", "set":False},
            ]}},
            {"deviceStatus": {**identity, "status": [
                {"statusCode":"F3", "valueType":"valueBinary", "valueBinary":{"code":None}},
                {"statusCode":"F1", "valueType":"valueBinary", "valueBinary":{"code":"00"*40}},
                {"statusCode":"private-key", "valueType":"private-secret"},
            ]}},
        ]), terminal_app_id="private-current")
        coordinator=SimpleNamespace(data={"private-key":device}, lock=asyncio.Lock(),
                                     client=client, last_update_success=True)
        entry=SimpleNamespace(runtime_data=coordinator, data={"password":"private-password"})
        result=await diagnostics.async_get_config_entry_diagnostics(None,entry)
        output=json.dumps(result)
        self.assertNotIn("private",output)
        self.assertNotIn("00"*40,output)
        record=result["devices"][0]
        self.assertEqual(record["humidity_pct"],50)
        self.assertEqual(record["deviceStatus"]["property_updated_at"],"2026-10-04T06:00:00")
        self.assertFalse(record["deviceStatus"]["fields"][0]["has_value"])
        self.assertEqual(record["deviceStatus"]["fields"][1]["payload_bytes"],40)
        self.assertFalse(record["deviceProperty"]["fields"][1]["set"])
        self.assertTrue(record["registration"]["paired"])
        self.assertTrue(record["registration"]["current_terminal_listed"])
        self.assertTrue(record["registration"]["current_terminal_uses_eu_app_descriptor"])
        self.assertEqual(record["registration"]["box_timezone"],"Europe/Warsaw")
        self.assertEqual([c.args[0] for c in client._hms_request.call_args_list],
                         ["setting/boxInfo","control/deviceProperty","control/deviceStatus"])
        self.assertEqual(client._hms_request.call_args_list[1].kwargs["extra_params"]["status"],"true")

    async def test_failure_messages_are_not_exported(self):
        device=SimpleNamespace(box_id="private-box", echonet_node="private-node",
            echonet_object="private-object", properties=SimpleNamespace())
        coordinator=SimpleNamespace(data={"private-key":device}, lock=asyncio.Lock(),
            client=SimpleNamespace(_hms_request=AsyncMock(side_effect=RuntimeError("private-token"))),
            last_update_success=False)
        result=await diagnostics.async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
        self.assertNotIn("private",json.dumps(result))
        self.assertEqual(result["devices"][0]["deviceStatus"]["error_type"],"RuntimeError")

    async def test_mismatched_device_metadata_is_not_exported(self):
        device=SimpleNamespace(device_id=1, echonet_node="node", echonet_object="obj")
        result=diagnostics.summarize({"deviceStatus":{"deviceId":2,"echonetNode":"node",
            "echonetObject":"obj","propertyUpdatedAt":"private-value","status":[]}},"deviceStatus",device)
        self.assertEqual(result,{"available":True,"identity_matches":False})

    async def test_registration_diagnostics_preserve_false_flags_and_hide_terminal_details(self):
        device = SimpleNamespace(box_id="private-box")
        client = SimpleNamespace(terminal_app_id="private-current",
                                 _pairing_errors={"private-box":"private-error"})
        response = {"box":[{"boxId":"private-box", "pairingFlag":False, "maxFlag":True,
            "pairedTerminalNum":10, "timezone":"private-value", "terminalAppInfo":[
                {"terminalAppId":"private-other", "appName":"private-app", "name":"private-name"}]}]}
        result = diagnostics.summarize_box(response, device, client)
        self.assertEqual(result, {"available":True, "paired":False, "terminal_limit_reached":True,
            "paired_terminal_count":10, "current_terminal_listed":False,
            "pairing_failed_during_login":True})
        self.assertNotIn("private",json.dumps(result))

    async def test_malformed_pairing_metadata_is_not_coerced_into_success(self):
        device = SimpleNamespace(box_id="private-box")
        client = SimpleNamespace(terminal_app_id="private-current")
        result = diagnostics.summarize_box({"box":[{"boxId":"private-box",
            "pairingFlag":"true", "maxFlag":"false", "pairedTerminalNum":True,
            "terminalAppInfo":[None, {"terminalAppId":"private-current", "appName":{}}]}]},device,client)
        self.assertNotIn("paired",result)
        self.assertNotIn("terminal_limit_reached",result)
        self.assertNotIn("paired_terminal_count",result)
        self.assertFalse(result["current_terminal_uses_eu_app_descriptor"])

    async def test_register_level_is_exported_only_for_matching_identity_and_bounded_integer(self):
        device = SimpleNamespace(device_id=1, echonet_node="node", echonet_object="obj")
        for level in (0, 1, "private", True, -1, 10000):
            result = diagnostics.summarize({"deviceStatus":{"deviceId":1, "echonetNode":"node",
                "echonetObject":"obj", "registerLevel":level, "status":[]}},"deviceStatus",device)
            if type(level) is int and 0 <= level <= 255:
                self.assertEqual(result["register_level"],level)
            else:
                self.assertNotIn("register_level",result)

    async def test_last_power_command_exports_outcome_without_identifiers_or_messages(self):
        device = SimpleNamespace(box_id="private-box", device_id=1, echonet_node="private-node",
            echonet_object="private-object", properties=SimpleNamespace())
        client = SimpleNamespace(_hms_request=AsyncMock(return_value={}), last_power_commands={
            ("private-box",1): {"requested_power":"off", "cloud_status":"error", "error_code":"E1004003",
                "state_confirmed":True, "outcome":"confirmed_by_state", "raw":"private-secret",
                "command_id":"private-command", "message":"private-response"}})
        coordinator = SimpleNamespace(data={"private-key":device}, lock=asyncio.Lock(),
            client=client,last_update_success=True)
        result = await diagnostics.async_get_config_entry_diagnostics(None,SimpleNamespace(runtime_data=coordinator))
        self.assertEqual(result["devices"][0]["last_power_command"], {
            "requested_power":"off", "cloud_status":"error", "error_code":"E1004003",
            "state_confirmed":True, "outcome":"confirmed_by_state"})
        self.assertNotIn("private",json.dumps(result))

    async def test_property_capabilities_and_embedded_status_are_summarized_separately(self):
        device = SimpleNamespace(device_id=1, echonet_node="private-node", echonet_object="private-object")
        response = {"deviceProperty":{"deviceId":1, "echonetNode":"private-node", "echonetObject":"private-object",
            "propertyUpdatedAt":"2026-10-04T16:44:09", "property":[
                {"statusCode":"80", "valueType":"valueSingle", "set":True, "get":True,
                 "valueSingle":[{"name":"private-on", "code":"30"},{"name":"private-off", "code":"31"}]},
                {"statusCode":"F3", "valueType":"valueBinary", "valueBinary":{"data":"private-schema"}},
            ], "status":[
                {"statusCode":"80", "valueType":"valueSingle", "valueSingle":{"code":"31"}},
                {"statusCode":"F3", "valueType":"valueBinary", "valueBinary":{"code":"00"*27}},
            ]}}
        result = diagnostics.summarize(response,"deviceProperty",device)
        self.assertTrue(result["fields"][0]["set"])
        self.assertNotIn("has_value",result["fields"][0])
        self.assertNotIn("has_value",result["fields"][1])
        self.assertTrue(result["current_status"]["fields"][0]["has_value"])
        self.assertEqual(result["current_status"]["fields"][1]["payload_bytes"],27)
        self.assertNotIn("private",json.dumps(result))
        self.assertNotIn("00"*27,json.dumps(result))
