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
        self.client._optional_live_properties = AsyncMock(return_value=None)

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

    async def test_bad_hex_only_removes_affected_readings(self):
        response = state()
        response["deviceStatus"]["status"][1]["valueBinary"]["code"] = "bad hex"
        self.client._hms_request = AsyncMock(return_value=response)
        with self.assertLogs(api.__name__, level="WARNING") as logs:
            device, = await self.client.get_devices()
        self.assertEqual(device.properties.power, "on")
        self.assertIsNone(device.properties.humidity_pct)
        self.assertIn("0xF1 (valueBinary)", logs.output[0])
        self.assertNotIn("bad hex", logs.output[0])

    async def test_range_energy_above_255_does_not_block_setup(self):
        # 0.1.5's bytes([int(value)]) raised ValueError for this valid counter.
        for value in ("256", "123456", 123456):
            with self.subTest(value=value):
                response = state()
                response["deviceStatus"]["status"].append({
                    "statusCode": "85", "valueType": "valueRange",
                    "valueRange": {"type": "int", "code": value},
                })
                self.client._hms_request = AsyncMock(return_value=response)
                device, = await self.client.get_devices()
                self.assertEqual(device.properties.energy_wh, int(value))
                self.assertEqual(device.properties.humidity_pct, 54)
                self.assertEqual(device.properties.power, "on")

    async def test_null_and_empty_fields_do_not_block_other_readings(self):
        for value in (None, "", "null"):
            with self.subTest(value=value):
                response = state()
                response["deviceStatus"]["status"].append({
                    "statusCode": "85", "valueType": "valueBinary",
                    "valueBinary": {"code": value},
                })
                self.client._hms_request = AsyncMock(return_value=response)
                device, = await self.client.get_devices()
                self.assertIsNone(device.properties.energy_wh)
                self.assertEqual(device.properties.humidity_pct, 54)

    async def test_malformed_optional_items_keep_valid_status(self):
        for item in (None, {}, {"statusCode": "85", "valueType": {}},
                     {"statusCode": "85", "valueType": "valueRange", "valueRange": {"code": "1.5"}},
                     {"statusCode": "85", "valueType": "valueRange", "valueRange": {"code": "-1"}},
                     {"statusCode": "F3", "valueType": "valueBinary", "valueBinary": {"code": "0100"}}):
            with self.subTest(item=item):
                response = state()
                response["deviceStatus"]["status"].append(item)
                self.client._hms_request = AsyncMock(return_value=response)
                with self.assertLogs(api.__name__, level="WARNING"):
                    device, = await self.client.get_devices()
                self.assertEqual(device.properties.humidity_pct, 54)
                self.assertEqual(device.properties.power, "on")

    async def test_only_invalid_status_still_raises_update_error(self):
        response = state()
        response["deviceStatus"]["status"] = [{
            "statusCode": "F1", "valueType": "valueBinary", "valueBinary": {"code": "invalid"},
        }]
        self.client._hms_request = AsyncMock(return_value=response)
        with self.assertLogs(api.__name__, level="WARNING"):
            with self.assertRaisesRegex(SharpApiError, "no usable status fields.*0xF1"):
                await self.client.get_devices()

    async def test_integer_single_code_matches_android_string_conversion(self):
        response = state()
        response["deviceStatus"]["status"][0]["valueSingle"]["code"] = 30
        self.client._hms_request = AsyncMock(return_value=response)
        device, = await self.client.get_devices()
        self.assertEqual(device.properties.power, "on")

    async def test_missing_controls_are_read_with_status_true_instead_of_capabilities_only(self):
        self.client._optional_live_properties = api.SharpLifeAirClient._optional_live_properties.__get__(self.client)
        status = state(50)
        status["deviceStatus"]["status"][0]["valueSingle"]["code"] = None
        property_state = state(54)["deviceStatus"]
        property_state["property"] = [{"statusCode":"80", "valueType":"valueSingle",
            "valueSingle":[{"code":"30","name":"On"},{"code":"31","name":"Off"}]}]
        property_state["propertyUpdatedAt"] = "2026-10-04T10:31:01"
        self.client._hms_request = AsyncMock(side_effect=[status,{"deviceProperty":property_state}])
        device, = await self.client.get_devices()
        self.assertEqual(device.properties.power,"on")
        self.assertEqual(device.properties.humidity_pct,54)
        self.assertEqual(device.updated_at,"2026-10-04T10:31:01")
        self.assertEqual(self.client._hms_request.call_args_list[-1].kwargs["extra_params"]["status"],"true")

    async def test_older_missing_or_incomparable_property_timestamp_cannot_replace_status(self):
        for timestamp in ("2026-10-04T10:30:59",None,"private-value","2026-10-04T10:31:01Z"):
            with self.subTest(timestamp=timestamp):
                self.client._optional_live_properties = api.SharpLifeAirClient._optional_live_properties.__get__(self.client)
                status = state(50)
                status["deviceStatus"]["status"][0]["valueSingle"]["code"] = None
                property_state = state(54)["deviceStatus"]
                property_state["property"] = [{"statusCode":"80", "valueType":"valueSingle",
                    "valueSingle":[{"code":"30","name":"On"},{"code":"31","name":"Off"}]}]
                property_state["propertyUpdatedAt"] = timestamp
                self.client._hms_request = AsyncMock(side_effect=[status,{"deviceProperty":property_state}])
                device, = await self.client.get_devices()
                self.assertIsNone(device.properties.power)
                self.assertEqual(device.properties.humidity_pct,50)

    async def test_failed_property_read_does_not_discard_valid_status(self):
        self.client._optional_live_properties = api.SharpLifeAirClient._optional_live_properties.__get__(self.client)
        self.client._hms_request = AsyncMock(side_effect=[state(54),SharpApiError("HTTP 503")])
        device, = await self.client.get_devices()
        self.assertEqual(device.properties.power,"on")
        self.assertEqual(device.properties.humidity_pct,54)

    async def test_property_schemas_do_not_generate_invalid_reading_warnings(self):
        # b6.l.f.c: property is decoded by l.i (capabilities), status by l.j
        # (current values). Keep both sections in the fixture, as in the APK.
        self.client._optional_live_properties = api.SharpLifeAirClient._optional_live_properties.__get__(self.client)
        status = state(50)
        status["deviceStatus"]["status"][0]["valueSingle"]["code"] = None
        current = state(54)["deviceStatus"]
        current["propertyUpdatedAt"] = "2026-10-04T10:31:01"
        current["property"] = [
            {"statusCode":"80", "valueType":"valueSingle", "get":True, "set":True,
             "valueSingle":[{"name":"On", "code":"30"},{"name":"Off", "code":"31"}]},
            {"statusCode":"84", "valueType":"valueRange",
             "valueRange":{"type":"int", "min":"0", "max":"65535", "step":"1", "unit":"W"}},
            {"statusCode":"F1", "valueType":"valueBinary", "valueBinary":{"data":"private-schema"}},
            {"statusCode":"F3", "valueType":"valueBinary", "valueBinary":{"data":"private-schema"}},
        ]
        f3 = bytearray(27)
        f3[4], f3[15] = 0x10, 0xFF
        current["status"].append({"statusCode":"F3", "valueType":"valueBinary",
                                  "valueBinary":{"code":f3.hex()}})
        self.client._hms_request = AsyncMock(side_effect=[status,{"deviceProperty":current}])
        with self.assertNoLogs(api.__name__,level="WARNING"):
            device, = await self.client.get_devices()
        self.assertEqual(device.properties.power,"on")
        self.assertEqual(device.properties.operation_mode,"Auto")
        self.assertTrue(device.properties.humidify)
        self.assertEqual(device.properties.humidity_pct,54)

    async def test_capabilities_without_status_cannot_supply_power_or_readback(self):
        response = {"deviceProperty":{"deviceId":1, "echonetNode":"node", "echonetObject":"013502",
            "propertyUpdatedAt":"2026-10-04T10:31:01", "property":[
                {"statusCode":"80", "valueType":"valueSingle", "valueSingle":{"code":"31"}},
            ]}}
        self.client._optional_live_properties = api.SharpLifeAirClient._optional_live_properties.__get__(self.client)
        self.client._hms_request = AsyncMock(return_value=response)
        with self.assertNoLogs(api.__name__,level="WARNING"):
            live = await self.client._optional_live_properties(
                type("Device",(),{"device_id":1,"box_id":"box","echonet_node":"node","echonet_object":"013502"})()
            )
        self.assertIsNone(live)


if __name__ == "__main__":
    unittest.main()
