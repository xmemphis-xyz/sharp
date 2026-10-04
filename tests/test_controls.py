"""Cloud command acknowledgement and completion regression tests."""
import asyncio
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiosharp_cocoro_air import SharpApiError, SharpAuthError

spec = importlib.util.spec_from_file_location(
    "cloud_controls_api", Path(__file__).parents[1] / "custom_components/sharp_life_air/api.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class ControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = api.SharpLifeAirClient("test@example.invalid", "fake")
        self.client._terminal_app_id = "fake-terminal"
        self.device = SimpleNamespace(box_id="fake-box", device_id=1,
                                      echonet_node="node", echonet_object="013502")
        self.sleep = patch.object(api.asyncio, "sleep", new=AsyncMock())
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def mock_responses(self, *responses):
        self.client._hms_request = AsyncMock(side_effect=responses)

    async def test_power_off_waits_for_matching_success(self):
        self.mock_responses(
            {"controlList": [{"id": "cmd", "errorCode": "null"}]},
            {"resultList": [{"id": "cmd", "status": "wait"}]},
            {"resultList": [{"id": "cmd", "status": "exec"}]},
            {"resultList": [{"id": "cmd", "status": "success"}]},
        )
        await self.client.power_off(self.device)
        calls = self.client._hms_request.call_args_list
        self.assertEqual(calls[0].args, ("control/deviceControl",))
        control = calls[0].kwargs["body"]["controlList"][0]
        self.assertEqual(control["echonetObject"], "013502")
        self.assertEqual(control["status"][0]["valueSingle"]["code"], "31")
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[-1].kwargs["body"], {"resultList": [{"id": "cmd"}]})

    async def test_mode_and_humidification_send_expected_library_controls(self):
        for method, argument, expected in (("set_mode", "auto", "10"), ("set_humidify", True, None)):
            with self.subTest(method=method):
                self.mock_responses(
                    {"controlList": [{"id": "cmd", "errorCode": None}]},
                    {"resultList": [{"id": "cmd", "status": "success"}]},
                )
                await getattr(self.client, method)(self.device, argument)
                status = self.client._hms_request.call_args_list[0].kwargs["body"]["controlList"][0]["status"]
                self.assertEqual(status[0]["statusCode"], "F3")
                if expected:
                    self.assertEqual(bytes.fromhex(status[0]["valueBinary"]["code"])[4], int(expected, 16))

    async def test_rejected_command_is_not_retried(self):
        self.mock_responses({"controlList": [{"id": "cmd", "errorCode": "rejected"}]})
        with self.assertRaises(SharpApiError):
            await self.client.power_on(self.device)
        self.assertEqual(self.client._hms_request.call_count, 1)

    async def test_missing_or_malformed_ack_is_rejected(self):
        for response in ({}, {"controlList": []}, {"controlList": [{"id": "cmd"}]},
                         {"controlList": [{"id": None, "errorCode": None}]}):
            self.mock_responses(response)
            with self.assertRaises(SharpApiError):
                await self.client.power_on(self.device)

    async def test_error_unmatch_and_unknown_status_are_not_success(self):
        for status in ("error", "unmatch", "cancelled", None):
            self.mock_responses(
                {"controlList": [{"id": "cmd", "errorCode": None}]},
                {"resultList": [{"id": "cmd", "status": status}]},
            )
            with self.assertRaises(SharpApiError):
                await self.client.power_on(self.device)
            self.assertEqual(self.client._hms_request.call_count, 2)

    async def test_other_command_result_cannot_confirm_our_command(self):
        self.mock_responses(
            {"controlList": [{"id": "cmd", "errorCode": None}]},
            {"resultList": [{"id": "other", "status": "success"}]},
        )
        with self.assertRaises(SharpApiError):
            await self.client.power_on(self.device)

    async def test_authentication_failure_propagates(self):
        self.mock_responses(SharpAuthError("expired"))
        with self.assertRaises(SharpAuthError):
            await self.client.power_on(self.device)

    async def test_timeout_does_not_repeat_the_write(self):
        self.mock_responses(
            {"controlList": [{"id": "cmd", "errorCode": None}]},
            TimeoutError(),
        )
        with self.assertRaises(TimeoutError):
            await self.client.power_off(self.device)
        self.assertEqual(sum(call.args[0] == "control/deviceControl"
                             for call in self.client._hms_request.call_args_list), 1)


if __name__ == "__main__":
    unittest.main()
