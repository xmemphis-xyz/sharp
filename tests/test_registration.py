"""Exercise authentication, pairing and controls through real local HTTP."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp import web
from aiosharp_cocoro_air import SharpApiError, SharpAuthError
import aiosharp_cocoro_air.api as upstream

spec = importlib.util.spec_from_file_location(
    "registration_api", Path(__file__).parents[1]/"custom_components/sharp_life_air/api.py"
)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class RegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.calls = []
        self.responses = {}
        self.paired = False
        self.confirm_pairing = True
        self.full = False
        self.allocated = 0
        self.live_properties = False
        self.executed = False
        self.apply_control = True
        self.advance_time = True
        self.mismatched_readback = False
        self.missing_power = False
        self.reported_power = "30"
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self.handle)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        base = f"http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}/"
        for module in (api, upstream):
            patcher = patch.object(module, "API_BASE", base)
            patcher.start()
            self.addCleanup(patcher.stop)
        oauth = patch.object(api, "async_obtain_auth_code", AsyncMock(return_value=("fake-code", "fake-nonce")))
        oauth.start()
        self.addCleanup(oauth.stop)
        sleep = patch.object(api.asyncio, "sleep", AsyncMock())
        sleep.start()
        self.addCleanup(sleep.stop)
        self.client = api.SharpLifeAirClient("test@example.invalid", "fake-password")
        self.addAsyncCleanup(self.client.close)
        self.addAsyncCleanup(self.runner.cleanup)
        self.device = SimpleNamespace(box_id="fake-box", device_id=1,
                                      echonet_node="node", echonet_object="013502")

    async def handle(self, request):
        path = request.path.lstrip("/")
        text = await request.text()
        data = json.loads(text) if text else None
        self.calls.append((request.method, path, dict(request.query), data))
        if path in self.responses:
            status, payload = self.responses[path]
            if isinstance(payload, str):
                return web.Response(status=status, text=payload)
            return web.json_response(payload, status=status)
        if path == "setting/terminalAppId/":
            self.allocated += 1
            return web.json_response({"terminalAppId": "fake-terminal"})
        if path == "setting/userInfo":
            return web.json_response({"userId": "fake-account"})
        if path == "setting/boxInfo":
            return web.json_response({"box": [{"boxId":"fake-box", "pairingFlag":self.paired,
                "maxFlag":self.full, "echonetData":[], "terminalAppInfo":[
                    {"terminalAppId":"unrelated-terminal", "appName":None},
                    {"terminalAppId":"other-ha", "appName":"spremote_ha_eu:1:1.0.0"}]}]})
        if path == "setting/pairing/":
            if self.confirm_pairing:
                self.paired = True
            return web.json_response({}, status=201)
        if path == "control/deviceProperty" and self.live_properties:
            return web.json_response({"deviceProperty": {
                "deviceId":2 if self.executed and self.mismatched_readback else 1,
                "echonetNode":"node", "echonetObject":"013502",
                "propertyUpdatedAt":"2026-10-04T15:41:01" if self.executed and self.advance_time else "2026-10-04T15:41:00",
                "property":[{"statusCode":"80", "valueType":"valueSingle", "valueSingle":{
                    "code":None if self.executed and self.missing_power else self.reported_power}}],
            }})
        if path == "control/deviceControl":
            self.executed = True
            if self.live_properties and self.apply_control:
                self.reported_power = data["controlList"][0]["status"][0]["valueSingle"]["code"]
            return web.json_response({"controlList":[{"id":"fake-command", "errorCode":None}]})
        if path == "control/controlResult":
            return web.json_response({"resultList":[{"id":"fake-command", "status":"success"}]})
        return web.json_response({})

    def calls_for(self, path):
        return [call for call in self.calls if call[1] == path]

    async def test_identity_reused_across_authentication_and_new_client(self):
        await self.client.authenticate()
        await self.client.authenticate()
        self.assertEqual(self.allocated, 1)
        other = api.SharpLifeAirClient("test@example.invalid", "fake-password",
                                     terminal_app_id=self.client.terminal_app_id)
        self.addAsyncCleanup(other.close)
        await other.authenticate()
        self.assertEqual(self.allocated, 1)
        self.assertEqual([call[3]["terminalAppId"] for call in self.calls_for("setting/login/")],
                         ["fake-terminal"] * 3)
        self.assertEqual(len(self.calls_for("setting/pairing/")), 1)

    async def test_registration_matches_eu_apk_and_never_deletes_other_terminals(self):
        await self.client.authenticate()
        registration, = self.calls_for("setting/terminal")
        self.assertEqual(registration[3], {"name":"HomeAssistant", "os":"Android", "osVersion":"14",
                                          "pushId":"", "appName":"spremote_a_eu:1:1.0.4"})
        pairing, = self.calls_for("setting/pairing/")
        self.assertEqual(pairing[0], "POST")
        self.assertEqual(pairing[2]["houseFlag"], "true")
        self.assertIsNone(pairing[3])  # The official pairing request has no body.
        self.assertFalse(any(call[0] == "PUT" for call in self.calls))

    async def test_rejected_registration_stops_before_pairing_and_control(self):
        self.responses["setting/terminal"] = (200, {"errorCode":"E1001001", "message":"private-response"})
        with self.assertRaisesRegex(SharpApiError, "setting/terminal: errorCode=E1001001"):
            await self.client.authenticate()
        self.assertFalse(self.calls_for("setting/pairing/"))
        self.assertFalse(self.calls_for("control/deviceControl"))

    async def test_failed_pairing_is_reported_and_cannot_send_control(self):
        self.responses["setting/pairing/"] = (503, {"message":"private-response"})
        with self.assertLogs(api.__name__, level="WARNING") as logs:
            await self.client.authenticate()
        self.assertEqual(self.client._pairing_errors, {"fake-box":"setting/pairing/: HTTP 503"})
        self.assertNotIn("private-response", str(logs.output))
        with self.assertRaisesRegex(SharpApiError, "setting/pairing/: HTTP 503"):
            await self.client.power_off(self.device)
        self.assertFalse(self.calls_for("control/deviceControl"))

    async def test_pairing_http_success_with_api_error_is_not_accepted(self):
        self.responses["setting/pairing/"] = (201, {"errorCode":"E1001002"})
        with self.assertLogs(api.__name__, level="WARNING"):
            await self.client.authenticate()
        with self.assertRaisesRegex(SharpApiError, "setting/pairing/: errorCode=E1001002"):
            await self.client.power_off(self.device)
        self.assertFalse(self.calls_for("control/deviceControl"))

    async def test_pairing_requires_readback_and_cannot_trust_http_success(self):
        self.confirm_pairing = False
        await self.client.authenticate()
        with self.assertRaisesRegex(SharpApiError, "pairing not confirmed; device command not sent"):
            await self.client.power_off(self.device)
        self.assertFalse(self.calls_for("control/deviceControl"))

    async def test_full_terminal_list_is_not_deleted_or_sent_a_command(self):
        self.full = True
        with self.assertLogs(api.__name__, level="WARNING"):
            await self.client.authenticate()
        with self.assertRaisesRegex(SharpApiError, "terminal limit reached"):
            await self.client.power_off(self.device)
        self.assertFalse(self.calls_for("setting/pairing/"))
        self.assertFalse(self.calls_for("control/deviceControl"))
        self.assertFalse(any(call[0] == "PUT" for call in self.calls))

    async def test_already_paired_at_limit_can_control_without_new_pairing(self):
        self.paired = self.full = True
        await self.client.authenticate()
        await self.client.power_off(self.device)
        self.assertFalse(self.calls_for("setting/pairing/"))
        self.assertEqual(len(self.calls_for("control/deviceControl")), 1)

    async def test_lost_pairing_is_reestablished_before_single_write(self):
        await self.client.authenticate()
        self.paired = False
        self.calls.clear()
        await self.client.power_off(self.device)
        self.assertEqual([call[1] for call in self.calls], [
            "control/deviceProperty", "setting/boxInfo", "setting/pairing/", "setting/boxInfo",
            "control/deviceControl", "control/controlResult",
        ])
        write, = self.calls_for("control/deviceControl")
        self.assertEqual(write[2]["terminalAppId"], "fake-terminal")
        self.assertEqual(write[3]["controlList"][0]["status"], [
            {"statusCode":"80", "valueType":"valueSingle", "valueSingle":{"code":"31"}},
        ])

    async def test_execution_error_after_valid_pairing_does_not_repeat_write(self):
        await self.client.authenticate()
        self.responses["control/controlResult"] = (200, {"resultList":[
            {"id":"fake-command", "status":"error", "errorCode":"E1004003"}]})
        with self.assertRaisesRegex(SharpApiError, "E1004003; fields=80"):
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")), 1)
        self.assertEqual(len(self.calls_for("setting/pairing/")), 1)

    async def test_top_level_http_success_error_is_not_authentication_success(self):
        self.responses["setting/login/"] = (200, {"errorCode":"E1001001"})
        with self.assertRaisesRegex(SharpApiError, "setting/login/: errorCode=E1001001"):
            await self.client.authenticate()
        self.assertFalse(self.calls_for("setting/terminal"))

    async def test_authentication_rejection_does_not_export_body(self):
        self.responses["setting/terminal"] = (403, {"message":"private-token"})
        with self.assertRaises(SharpAuthError) as ctx:
            await self.client.authenticate()
        self.assertNotIn("private", str(ctx.exception))

    async def test_http_errors_expose_endpoint_and_status_without_body(self):
        self.responses["control/deviceStatus"] = (500, "private-response")
        with self.assertRaises(SharpApiError) as ctx:
            await self.client._hms_request("control/deviceStatus")
        self.assertEqual(str(ctx.exception), "control/deviceStatus: HTTP 500")

    async def test_malformed_registration_response_is_not_success(self):
        for payload in ("not JSON private-response", ["private-id"]):
            with self.subTest(payload=payload):
                self.responses["setting/terminal"] = (200, payload)
                with self.assertRaises(SharpApiError) as ctx:
                    await self.client._register_terminal()
                self.assertNotIn("private", str(ctx.exception))

    async def test_arbitrary_top_level_error_code_is_not_logged(self):
        self.responses["setting/boxInfo"] = (200, {"errorCode":"private-user-identity"})
        with self.assertRaisesRegex(SharpApiError, "errorCode=unknown") as ctx:
            await self.client._get_boxes()
        self.assertNotIn("private", str(ctx.exception))

    async def test_invalid_terminal_identity_is_rejected(self):
        for value in (None, "", [], 123):
            with self.subTest(value=value):
                self.responses["setting/terminalAppId/"] = (200, {"terminalAppId":value})
                with self.assertRaisesRegex(SharpApiError, "invalid terminal identity"):
                    await self.client.authenticate()
        self.assertFalse(self.calls_for("setting/login/"))

    async def prepare_execution_error(self, code="E1004003", state="error"):
        self.live_properties = True
        await self.client.authenticate()
        self.responses["control/controlResult"] = (200, {"resultList":[
            {"id":"fake-command", "status":state, "errorCode":code}]})

    async def test_reported_physical_off_can_be_confirmed_by_newer_exact_device_state(self):
        await self.prepare_execution_error()
        with self.assertLogs(api.__name__, level="WARNING") as logs:
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")),1)
        self.assertEqual(len(self.calls_for("control/deviceProperty")),2)
        self.assertTrue(all(call[2]["status"] == "true" for call in self.calls_for("control/deviceProperty")))
        self.assertIn("newer deviceProperty state confirmed power off",str(logs.output))
        self.assertEqual(self.client.last_power_commands[("fake-box",1)], {
            "requested_power":"off", "cloud_status":"error", "error_code":"E1004003",
            "state_confirmed":True, "outcome":"confirmed_by_state",
        })

    async def test_power_on_error_can_be_confirmed_without_changing_or_repeating_payload(self):
        self.reported_power = "31"
        await self.prepare_execution_error()
        with self.assertLogs(api.__name__, level="WARNING"):
            await self.client.power_on(self.device)
        write, = self.calls_for("control/deviceControl")
        self.assertEqual(write[3]["controlList"][0]["status"], [
            {"statusCode":"80", "valueType":"valueSingle", "valueSingle":{"code":"30"}},
        ])
        self.assertTrue(self.client.last_power_commands[("fake-box",1)]["state_confirmed"])

    async def test_opposite_readback_still_raises_original_error(self):
        self.apply_control = False
        await self.prepare_execution_error()
        with self.assertRaisesRegex(SharpApiError,"E1004003; fields=80"):
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")),1)
        self.assertEqual(len(self.calls_for("control/deviceProperty")),4)
        self.assertFalse(self.client.last_power_commands[("fake-box",1)]["state_confirmed"])

    async def test_cached_matching_state_is_not_confirmation(self):
        self.advance_time = False
        self.reported_power = "31"
        await self.prepare_execution_error()
        with self.assertRaisesRegex(SharpApiError,"E1004003; fields=80"):
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")),1)

    async def test_absent_power_value_is_not_confirmation(self):
        self.missing_power = True
        await self.prepare_execution_error()
        with self.assertRaisesRegex(SharpApiError,"E1004003; fields=80"):
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")),1)

    async def test_other_device_readback_is_not_confirmation(self):
        self.mismatched_readback = True
        await self.prepare_execution_error()
        with self.assertRaisesRegex(SharpApiError,"E1004003; fields=80"):
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")),1)

    async def test_unavailable_baseline_does_not_prevent_write_or_hide_error(self):
        await self.prepare_execution_error()
        self.responses["control/deviceProperty"] = (503,{"message":"private-response"})
        with self.assertRaisesRegex(SharpApiError,"E1004003; fields=80"):
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")),1)
        self.assertEqual(len(self.calls_for("control/deviceProperty")),1)

    async def test_other_error_and_unmatch_cannot_use_matching_state_to_suppress_failure(self):
        for state, code in (("error","E1004002"),("unmatch","E1004003")):
            with self.subTest(state=state):
                await self.prepare_execution_error(code,state)
                self.calls.clear()
                with self.assertRaises(SharpApiError):
                    await self.client.power_off(self.device)
                self.assertEqual(len(self.calls_for("control/deviceControl")),1)
                self.assertEqual(len(self.calls_for("control/deviceProperty")),1)

    async def test_missing_baseline_timestamp_does_not_allow_confirmation(self):
        await self.prepare_execution_error()
        self.responses["control/deviceProperty"] = (200, {"deviceProperty": {
            "deviceId":1, "echonetNode":"node", "echonetObject":"013502",
            "property":[{"statusCode":"80", "valueType":"valueSingle", "valueSingle":{"code":"31"}}],
        }})
        with self.assertRaisesRegex(SharpApiError,"E1004003; fields=80"):
            await self.client.power_off(self.device)
        self.assertEqual(len(self.calls_for("control/deviceControl")),1)
        self.assertEqual(len(self.calls_for("control/deviceProperty")),1)
