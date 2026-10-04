"""Regression coverage for deviceStatus rather than cached boxInfo readings."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from aiosharp_cocoro_air import SharpApiError, SharpCOCOROAir

spec = importlib.util.spec_from_file_location(
    "status_api", Path(__file__).parents[1] / "custom_components/sharp_life_air/api.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


def state(humidity=54):
    f1 = bytearray(40)
    f1[3:5] = bytes([22, humidity])
    return {"deviceStatus": {
        "deviceId": 1, "echonetNode": "node", "echonetObject": "013502",
        "propertyUpdatedAt": "2026-10-04T10:31:00",
        "status": [
            {"statusCode": "80", "valueType": "valueSingle", "valueSingle": {"code": "30"}},
            {"statusCode": "F1", "valueType": "valueBinary", "valueBinary": {"code": f1.hex()}},
        ],
    }}


class StatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = api.SharpLifeAirClient("test@example.invalid", "fake")
        f1 = bytearray(40)
        f1[3:5] = bytes([22, 50])
        self.boxes = {"box": [{"boxId": "box", "echonetData": [{
            "deviceId": 1, "echonetNode": "node", "echonetObject": "013502",
            "model": "KITX100EU", "labelData": {"name": "Purifier"},
            "echonetProperty": "0000000000000000f128" + f1.hex(),
        }]}]}
        self.client._get_boxes = AsyncMock(return_value=self.boxes)

    async def test_live_status_replaces_cached_humidity_and_preserves_identity(self):
        self.client._hms_request = AsyncMock(return_value=state())
        device, = await self.client.get_devices()
        self.assertEqual(device.properties.humidity_pct, 54)
        self.assertEqual(device.properties.power, "on")
        self.assertEqual(device.model, "KITX100EU")
        self.assertEqual(device.name, "Purifier")
        self.assertEqual(device.updated_at, "2026-10-04T10:31:00")
        self.client._hms_request.assert_awaited_once_with(
            "control/deviceStatus", extra_params={"boxId": "box", "echonetNode": "node",
                                                   "echonetObject": "013502"})

    async def test_missing_live_humidity_does_not_reuse_cached_50(self):
        response = state()
        response["deviceStatus"]["status"][1]["valueBinary"]["code"] = None
        self.client._hms_request = AsyncMock(return_value=response)
        device, = await self.client.get_devices()
        self.assertIsNone(device.properties.humidity_pct)
        self.assertEqual(device.properties.power, "on")

    async def test_malformed_status_is_not_a_successful_update(self):
        for response in ({}, {"deviceStatus": {}}, {"deviceStatus": None}):
            self.client._hms_request = AsyncMock(return_value=response)
            with self.assertRaises(SharpApiError):
                await self.client.get_devices()

    async def test_another_device_cannot_supply_readings(self):
        response = state()
        response["deviceStatus"]["deviceId"] = 2
        self.client._hms_request = AsyncMock(return_value=response)
        with self.assertRaisesRegex(SharpApiError, "mismatched device"):
            await self.client.get_devices()

    async def test_http_errors_expose_endpoint_and_status_without_body(self):
        with patch.object(SharpCOCOROAir, "_hms_request", new=AsyncMock(
            side_effect=SharpApiError("API error 500 on control/deviceStatus: private body")
        )):
            with self.assertRaises(SharpApiError) as ctx:
                await self.client._hms_request("control/deviceStatus")
        self.assertEqual(str(ctx.exception), "control/deviceStatus: HTTP 500")

    async def test_bad_hex_is_reported_as_api_error(self):
        response = state()
        response["deviceStatus"]["status"][1]["valueBinary"]["code"] = "bad hex"
        self.client._hms_request = AsyncMock(return_value=response)
        with self.assertRaisesRegex(SharpApiError, "invalid status value"):
            await self.client.get_devices()


if __name__ == "__main__":
    unittest.main()
