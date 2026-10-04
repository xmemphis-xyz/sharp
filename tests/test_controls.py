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
        # Pairing is exercised independently through its real request sequence.
        self.client._ensure_paired = AsyncMock()
        self.client._optional_live_properties = AsyncMock(return_value=None)
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
        self.assertEqual(control["status"], [{"statusCode": "80", "valueType": "valueSingle",
                                            "valueSingle": {"code": "31"}}])
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

    async def test_commands_match_apk_update_bitmap(self):
        # Golden vectors from c6.h.a/c6.a in Life AIR 1.0.4, not upstream
        # library constants (which set additional update bits).
        cases = (
            ("set_mode", ("auto",), "010000001000000000000000000000000000000000000000000000"),
            ("set_humidify", (True,), "000800000000000000000000000000FF0000000000000000000000"),
            ("set_humidify", (False,), "000800000000000000000000000000000000000000000000000000"),
        )
        for method, args, expected in cases:
            with self.subTest(method=method, args=args):
                self.mock_responses(
                    {"controlList": [{"id": "cmd", "errorCode": None}]},
                    {"resultList": [{"id": "cmd", "status": "success"}]},
                )
                await getattr(self.client, method)(self.device, *args)
                status = self.client._hms_request.call_args_list[0].kwargs["body"]["controlList"][0]["status"]
                self.assertEqual(status[-1]["valueBinary"]["code"], expected)

    async def test_power_uses_only_standard_operation_status(self):
        for method, code in (("power_on", "30"), ("power_off", "31")):
            with self.subTest(method=method):
                self.mock_responses(
                    {"controlList": [{"id": "cmd", "errorCode": None}]},
                    {"resultList": [{"id": "cmd", "status": "success"}]},
                )
                await getattr(self.client, method)(self.device)
                controls = self.client._hms_request.call_args_list[0].kwargs["body"]["controlList"]
                self.assertEqual(len(controls), 1)
                self.assertEqual(controls[0]["status"], [
                    {"statusCode": "80", "valueType": "valueSingle", "valueSingle": {"code": code}}
                ])

    async def test_reported_execution_error_keeps_failure_and_identifies_fields(self):
        self.mock_responses(
            {"controlList": [{"id": "private-command", "errorCode": None}]},
            {"resultList": [{"id": "private-command", "status": "error",
                             "errorCode": "E1004003", "message": "private-response"}]},
        )
        with self.assertRaises(SharpApiError) as ctx:
            await self.client.power_off(self.device)
        self.assertEqual(str(ctx.exception),
                         "controlResult: status=error, errorCode=E1004003; fields=80")
        self.assertEqual(self.client._hms_request.call_count, 2)

    async def test_mode_error_identifies_proprietary_field(self):
        self.mock_responses(
            {"controlList": [{"id": "cmd", "errorCode": None}]},
            {"resultList": [{"id": "cmd", "status": "error", "errorCode": "E1004003"}]},
        )
        with self.assertRaisesRegex(SharpApiError, "fields=F3"):
            await self.client.set_mode(self.device, "auto")
        self.assertEqual(self.client._hms_request.call_count, 2)

    async def test_rejection_exposes_error_code(self):
        self.mock_responses({"controlList": [{"id": "cmd", "errorCode": "E123"}]})
        with self.assertRaisesRegex(SharpApiError, "deviceControl.*E123"):
            await self.client.power_off(self.device)

    async def test_multiple_acknowledgements_are_all_confirmed(self):
        self.mock_responses(
            {"controlList": [{"id": "power", "errorCode": None},
                             {"id": "f3", "errorCode": "null"}]},
            {"resultList": [{"id": "f3", "status": "wait"},
                            {"id": "power", "status": "success"}]},
            {"resultList": [{"id": "f3", "status": "exec"}]},
            {"resultList": [{"id": "f3", "status": "success"}]},
        )
        await self.client.power_off(self.device)
        calls = self.client._hms_request.call_args_list
        self.assertEqual(calls[1].kwargs["body"],
                         {"resultList": [{"id": "power"}, {"id": "f3"}]})
        self.assertEqual(calls[2].kwargs["body"], {"resultList": [{"id": "f3"}]})
        self.assertEqual(calls[3].kwargs["body"], {"resultList": [{"id": "f3"}]})
        self.assertEqual(sum(c.args[0] == "control/deviceControl" for c in calls), 1)

    async def test_one_failed_batch_entry_prevents_success(self):
        for status in ("error", "unmatch", "cancelled"):
            with self.subTest(status=status):
                self.mock_responses(
                    {"controlList": [{"id": "power", "errorCode": None},
                                     {"id": "f3", "errorCode": None}]},
                    {"resultList": [{"id": "power", "status": "success"},
                                    {"id": "f3", "status": status, "errorCode": "E456"}]},
                )
                with self.assertRaises(SharpApiError):
                    await self.client.power_off(self.device)
                self.assertEqual(self.client._hms_request.call_count, 2)

    async def test_partly_rejected_acknowledgement_is_not_success(self):
        self.mock_responses({"controlList": [{"id": "power", "errorCode": None},
                                            {"id": "f3", "errorCode": "E123"}]})
        with self.assertRaisesRegex(SharpApiError, "deviceControl.*E123"):
            await self.client.power_off(self.device)
        self.assertEqual(self.client._hms_request.call_count, 1)

    async def test_duplicate_and_non_scalar_ids_are_rejected(self):
        for ids in (("same", "same"), ("1", 1), ("cmd", []), ("cmd", {}), (True,)):
            with self.subTest(ids=ids):
                self.mock_responses({"controlList": [{"id": value, "errorCode": None}
                                                    for value in ids]})
                with self.assertRaises(SharpApiError):
                    await self.client.power_off(self.device)
                self.assertEqual(self.client._hms_request.call_count, 1)

    async def test_missing_extra_and_duplicate_batch_results_are_rejected(self):
        for items in ([{"id": "power", "status": "success"}],
                      [{"id": "power", "status": "success"},
                       {"id": "other", "status": "success"}],
                      [{"id": "power", "status": "success"},
                       {"id": "power", "status": "success"}],
                      [None, {"id": "f3", "status": "success"}]):
            with self.subTest(items=items):
                self.mock_responses(
                    {"controlList": [{"id": "power", "errorCode": None},
                                     {"id": "f3", "errorCode": None}]},
                    {"resultList": items},
                )
                with self.assertRaises(SharpApiError):
                    await self.client.power_off(self.device)

    async def test_invalid_acknowledgement_reports_safe_structure(self):
        responses = (
            ({"private-account": "secret"}, "controlList=missing"),
            ({"controlList": []}, "controlList=list; count=0"),
            ({"controlList": "secret"}, "controlList=str"),
            (["private-device"], "response=list"),
        )
        for response, expected in responses:
            with self.subTest(response=response):
                self.mock_responses(response)
                with self.assertRaises(SharpApiError) as ctx:
                    await self.client.power_off(self.device)
                self.assertIn("deviceControl: invalid acknowledgement", str(ctx.exception))
                self.assertIn(expected, str(ctx.exception))
                for private in ("private-account", "secret", "private-device"):
                    self.assertNotIn(private, str(ctx.exception))

    async def test_timeout_after_partial_success_does_not_repeat_write(self):
        self.mock_responses(
            {"controlList": [{"id": "power", "errorCode": None},
                             {"id": "f3", "errorCode": None}]},
            {"resultList": [{"id": "power", "status": "success"},
                            {"id": "f3", "status": "wait"}]},
            TimeoutError(),
        )
        with self.assertRaises(TimeoutError):
            await self.client.power_off(self.device)
        self.assertEqual(sum(c.args[0] == "control/deviceControl"
                             for c in self.client._hms_request.call_args_list), 1)

    async def test_top_level_error_reports_only_protocol_code(self):
        for code, expected in (("E1001001", "E1001001"),
                               ("private@example.invalid", "unknown")):
            self.mock_responses({"errorCode": code, "message": "private-response"})
            with self.assertRaises(SharpApiError) as ctx:
                await self.client.power_off(self.device)
            self.assertIn("errorCode=" + expected, str(ctx.exception))
            self.assertNotIn("private", str(ctx.exception))
            self.assertEqual(self.client._hms_request.call_count, 1)

    async def test_scalar_ids_match_android_string_conversion(self):
        self.mock_responses(
            {"controlList": [{"id": 123, "errorCode": None}]},
            {"resultList": [{"id": "123", "status": "success"}]},
        )
        await self.client.power_off(self.device)
        self.assertEqual(self.client._hms_request.call_args_list[1].kwargs["body"],
                         {"resultList": [{"id": 123}]})

    async def test_result_error_exposes_status_and_error_code(self):
        self.mock_responses(
            {"controlList": [{"id": "cmd", "errorCode": None}]},
            {"resultList": [{"id": "cmd", "status": "error", "errorCode": "E456"}]},
        )
        with self.assertRaisesRegex(SharpApiError, "controlResult.*error.*E456"):
            await self.client.power_off(self.device)

    async def test_result_message_and_identifiers_are_not_exposed(self):
        self.mock_responses(
            {"controlList": [{"id": "private-command", "errorCode": None}]},
            {"resultList": [{"id": "private-command", "status": "error",
                             "errorCode": "private@example.invalid", "message": "secret"}]},
        )
        with self.assertRaises(SharpApiError) as ctx:
            await self.client.power_off(self.device)
        for private in ("private-command", "private@example.invalid", "secret"):
            self.assertNotIn(private, str(ctx.exception))

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
