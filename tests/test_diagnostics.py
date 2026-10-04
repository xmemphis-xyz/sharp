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
            {"deviceProperty": {**identity, "property": [
                {"statusCode":"80", "valueType":"valueSingle", "set":True, "get":True},
                {"statusCode":"F3", "valueType":"valueBinary", "set":False},
            ]}},
            {"deviceStatus": {**identity, "status": [
                {"statusCode":"F3", "valueType":"valueBinary", "valueBinary":{"code":None}},
                {"statusCode":"F1", "valueType":"valueBinary", "valueBinary":{"code":"00"*40}},
                {"statusCode":"private-key", "valueType":"private-secret"},
            ]}},
        ]))
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
        self.assertEqual([c.args[0] for c in client._hms_request.call_args_list],
                         ["control/deviceProperty","control/deviceStatus"])

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
