"""Sharp EU cloud adapter, matching the Life AIR 1.0.4 APK."""
import asyncio
import json
import logging
import re
from dataclasses import fields, replace
from datetime import datetime
from urllib.parse import urlencode

import aiohttp
from aiosharp_cocoro_air import (
    SharpCOCOROAir, SharpApiError, SharpAuthError, SharpConnectionError,
    decode_echonet_property,
)
from aiosharp_cocoro_air.api import API_BASE, APP_SECRET
from aiosharp_cocoro_air.auth import async_obtain_auth_code
from aiosharp_cocoro_air.models import DeviceProperties

_LOGGER = logging.getLogger(__name__)
_STATUS_CODES = {0x80, 0x84, 0x85, 0x88, 0x8B, 0xA0, 0xC0, 0xF1, 0xF3}
_APP_NAME = "spremote_a_eu:1:1.0.4"


class SharpCommandResultError(SharpApiError):
    """A matched command's execution error, with bounded protocol metadata."""

    def __init__(self, state, code, requested_fields):
        self.state = error_code(state)
        self.code = error_code(code)
        super().__init__(f"controlResult: status={self.state}, errorCode={self.code}; "
                         f"fields={requested_fields or 'unknown'}")


def state_timestamp(value):
    """Parse a protocol timestamp without assuming a timezone."""
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", value
    ):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def at_least_as_recent(candidate, baseline, *, strictly=False):
    """Do not compare missing timestamps or mix naive/aware server clocks."""
    first, second = state_timestamp(candidate), state_timestamp(baseline)
    if first is None or second is None:
        return False
    try:
        return first > second if strictly else first >= second
    except TypeError:
        return False


def device_state(response, field, device):
    """Decode only the exact requested device from a live status response."""
    data = response.get(field) if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise SharpApiError(f"{field}: missing device status")
    if any(str(data.get(key)) != str(expected) for key, expected in (
        ("deviceId", device.device_id), ("echonetNode", device.echonet_node),
        ("echonetObject", device.echonet_object),
    )):
        raise SharpApiError(f"{field}: mismatched device")
    # Both endpoints store live values in status. deviceProperty.property
    # contains schemas (enumerations/ranges/binary definitions), never readings.
    return decode_status(data.get("status")), data.get("propertyUpdatedAt")


def check_api_response(response, endpoint):
    """An HTTP success can still contain a Sharp API error."""
    if not isinstance(response, dict):
        raise SharpApiError(f"{endpoint}: invalid API response")
    code = response.get("errorCode")
    if code not in (None, "", "null"):
        safe = str(code) if re.fullmatch(r"(?:E[0-9]{7}|[0-9]{3})", str(code)) else "unknown"
        raise SharpApiError(f"{endpoint}: errorCode={safe}")
    return response


def error_code(value):
    """Expose only bounded protocol codes, never arbitrary server messages."""
    code = str(value)
    return code if re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code) else "unknown"


def response_shape(response, field):
    """Describe only a known field's structure, never response data or keys."""
    def kind(value):
        return type(value).__name__ if type(value) in (
            dict, list, str, int, float, bool, type(None)
        ) else "unknown"

    shape = f"response={kind(response)}"
    if isinstance(response, dict) and "errorCode" in response:
        code = response["errorCode"]
        safe = str(code) if re.fullmatch(r"(?:E[0-9]{7}|[0-9]{3}|null)", str(code)) else "unknown"
        shape += f"; errorCode={safe}"
    if not isinstance(response, dict) or field not in response:
        return f"{shape}; {field}=missing"
    value = response[field]
    shape += f"; {field}={kind(value)}"
    if isinstance(value, list):
        shape += f"; count={len(value)}"
    return shape


def command_identifier(item, endpoint="deviceControl"):
    """Accept JSON scalar IDs, as Android getString does, without logging them."""
    value = item.get("id") if isinstance(item, dict) else None
    if (not isinstance(value, (str, int)) or isinstance(value, bool)
            or not str(value).strip() or len(str(value)) > 512):
        raise SharpApiError(f"{endpoint}: missing or invalid command identifier")
    return value


def f3_control(index: int, value: int) -> dict:
    """Build c6.h.a's four-byte update bitmap and 23-byte data payload.

    Indexes are one-based, as in the APK. Only the requested field is marked
    for update; zeroes in other fields do not overwrite device settings.
    """
    data = bytearray(27)
    bit = index - 5
    data[bit // 8] = 1 << (bit % 8)
    data[index - 1] = value
    return {"statusCode": "F3", "valueType": "valueBinary",
            "valueBinary": {"code": data.hex().upper()}}


def decode_status(status):
    """Decode independent status fields without losing other valid readings."""
    if not isinstance(status, list):
        raise SharpApiError("deviceStatus: missing status list")
    properties = {}
    invalid = []
    for item in status:
        code = None
        kind = None
        try:
            code = int(item["statusCode"], 16)
            if code not in _STATUS_CODES:
                continue
            kind = item["valueType"]
            if kind not in {"valueSingle", "valueRange", "valueBinary"}:
                raise ValueError("Unknown value type")
            value = item[kind]["code"]
            if value in (None, "", "null"):
                continue
            # Range values use decimal text; single/binary values use hex.
            if kind == "valueRange":
                if code not in {0x80, 0x84, 0x85, 0x88, 0xA0, 0xC0}:
                    raise ValueError("Range type for binary data")
                if not re.fullmatch(r"\d{1,20}", str(value)):
                    raise ValueError("Invalid unsigned integer")
                number = int(value)
                width = max(1, (number.bit_length() + 7) // 8)
                payload = number.to_bytes(width, "big")
            else:
                # Android getString also accepts integer JSON scalar codes.
                if not isinstance(value, (str, int)) or isinstance(value, bool):
                    raise ValueError("Invalid hex scalar")
                payload = bytes.fromhex(str(value))
            if not payload:
                continue
            if len(payload) > 255:
                raise ValueError("Property exceeds TLV length")
            if code in {0x80, 0x88, 0xA0, 0xC0} and len(payload) != 1:
                raise ValueError("Single-byte property has wrong length")
            if code in {0xF1, 0xF3} and len(payload) < 5:
                raise ValueError("Truncated Sharp state")
            data = bytes(8) + bytes([code, len(payload)]) + payload
            properties.update(decode_echonet_property(data.hex()))
        except (KeyError, TypeError, ValueError, OverflowError, IndexError):
            # Log only field/type, never account/device IDs or raw payloads.
            field = f"0x{code:02X}" if code in _STATUS_CODES else "unknown"
            value_type = kind if isinstance(kind, str) and kind in {
                "valueSingle", "valueRange", "valueBinary"
            } else "unknown"
            invalid.append(field)
            _LOGGER.warning("deviceStatus: ignored invalid field %s (%s)", field, value_type)
    if invalid and not properties:
        raise SharpApiError("deviceStatus: no usable status fields; invalid: " + ", ".join(invalid))
    return DeviceProperties(**properties)


def sanitize_properties(value: str | None) -> str:
    """Omit zero-length TLVs; they mean missing data, not a device state."""
    if not value:
        return ""
    try:
        data = bytes.fromhex(value)
    except (TypeError, ValueError) as err:
        raise SharpApiError("Invalid ECHONET property data") from err
    if len(data) < 8:
        return ""
    result = bytearray(data[:8])
    offset = 8
    while offset + 1 < len(data):
        length = data[offset + 1]
        end = offset + 2 + length
        if end > len(data):
            break
        if length:
            result.extend(data[offset:end])
        offset = end
    return result.hex()


class SharpLifeAirClient(SharpCOCOROAir):
    """Adapt the pinned library without modifying its global decoder."""

    def __init__(self, email, password, session=None, *, terminal_app_id=None):
        super().__init__(email, password, session)
        self._terminal_app_id = terminal_app_id
        self._pairing_errors = {}
        self.last_power_commands = {}

    @property
    def terminal_app_id(self):
        """Private identity for HA configuration storage, never diagnostics."""
        return self._terminal_app_id

    async def authenticate(self):
        # The APK retains this identity. Allocating another on each HA login
        # fills pairing slots and disconnects other clients during cleanup.
        if self._terminal_app_id is None:
            response = await self._hms_request("setting/terminalAppId/")
            value = response.get("terminalAppId")
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise SharpApiError("setting/terminalAppId/: invalid terminal identity")
            self._terminal_app_id = value
        auth_code, nonce = await async_obtain_auth_code(self._email, self._password)
        await self._hms_request("setting/login/", method="POST", body={
            "terminalAppId": self._terminal_app_id, "tempAccToken": auth_code,
            "password": nonce,
        }, extra_params={"serviceName": "sharp-eu"})
        info = await self._hms_request("setting/userInfo", extra_params={
            "terminalAppId": self._terminal_app_id,
        })
        self._user_id = info.get("userId")
        await self._register_terminal()
        await self._pair_boxes()

    async def _setting_post(self, path, *, body=None, extra_params=None):
        """Read and validate registration/pairing responses without logging IDs."""
        params = {"appSecret": APP_SECRET, **(extra_params or {})}
        url = f"{API_BASE}{path}?{urlencode(params)}"
        try:
            async with await self._ensure_session().post(url, json=body) as response:
                if response.status in (401, 403):
                    raise SharpAuthError(f"{path}: authentication rejected")
                if response.status not in (200, 201):
                    raise SharpApiError(f"{path}: HTTP {response.status}")
                payload = await response.text()
                try:
                    data = json.loads(payload) if payload else {}
                except ValueError:
                    raise SharpApiError(f"{path}: invalid JSON response") from None
                return check_api_response(data, path)
        except aiohttp.ClientError:
            raise SharpConnectionError(f"{path}: connection failed") from None

    async def _register_terminal(self):
        # Official EU descriptor from o5.t0 / b6.p.A in Life AIR 1.0.4.
        await self._setting_post("setting/terminal", body={
            "name": "HomeAssistant", "os": "Android", "osVersion": "14",
            "pushId": "", "appName": _APP_NAME,
        })

    async def _pair_box(self, box):
        if box.get("maxFlag") is True:
            raise SharpApiError("setting/pairing/: terminal limit reached")
        await self._setting_post("setting/pairing/", extra_params={
            "boxId": box["boxId"], "houseFlag": "true",
        })

    async def _pair_boxes(self):
        # Never delete registrations belonging to another HA instance or app.
        boxes = await self._get_boxes()
        self._pairing_errors.clear()
        for box in boxes["box"]:
            if box.get("pairingFlag") is True:
                continue
            try:
                await self._pair_box(box)
            except (SharpApiError, SharpConnectionError, TimeoutError) as err:
                # Keep valid sensor reads available, but expose the failure and
                # require fresh, confirmed pairing before any device write.
                detail = str(err) if isinstance(err, SharpApiError) else "connection or timeout"
                self._pairing_errors[box["boxId"]] = detail
                _LOGGER.warning("Sharp pairing failed: %s", detail)

    async def _ensure_paired(self, device):
        """The official app requires pairingFlag; discovery alone is not enough."""
        boxes = await self._get_boxes()
        box = next((box for box in boxes["box"] if box["boxId"] == device.box_id), None)
        if box is None:
            raise SharpApiError("setting/boxInfo: command device is missing")
        if box.get("pairingFlag") is not True:
            await self._pair_box(box)
            boxes = await self._get_boxes()
            box = next((box for box in boxes["box"] if box["boxId"] == device.box_id), None)
            if box is None or box.get("pairingFlag") is not True:
                raise SharpApiError("setting/pairing/: pairing not confirmed; device command not sent")
        self._pairing_errors.pop(device.box_id, None)

    async def _hms_request(self, path, *args, **kwargs):
        try:
            response = await super()._hms_request(path, *args, **kwargs)
        except ValueError:
            raise SharpApiError(f"{path}: invalid JSON response") from None
        except SharpApiError as err:
            # Upstream embeds raw response text in errors, possibly with IDs.
            match = re.match(r"API error (\d{3}) on ", str(err))
            detail = f"HTTP {match[1]}" if match else "invalid API response"
            raise SharpApiError(f"{path}: {detail}") from None
        except SharpAuthError:
            raise SharpAuthError(f"{path}: authentication rejected") from None
        except SharpConnectionError:
            raise SharpConnectionError(f"{path}: connection failed") from None
        return check_api_response(response, path)

    async def get_devices(self):
        devices = await super().get_devices()
        current = []
        for device in devices:
            response = await self._hms_request(
                "control/deviceStatus", extra_params={
                    "boxId": device.box_id, "echonetNode": device.echonet_node,
                    "echonetObject": device.echonet_object,
                },
            )
            properties, updated_at = device_state(response, "deviceStatus", device)
            if any(getattr(properties, key) is None for key in ("power", "operation_mode", "humidify")):
                # The app's deviceProperty request includes status=true. Without
                # it, this endpoint only reports capabilities, not current state.
                live = await self._optional_live_properties(device)
                if live is not None and at_least_as_recent(live[1], updated_at):
                    extra, updated_at = live
                    properties = replace(properties, **{
                        field.name: getattr(extra, field.name) for field in fields(extra)
                        if getattr(extra, field.name) is not None
                    })
            # Do not fill missing readings with stale boxInfo values.
            current.append(replace(device, properties=properties, updated_at=updated_at))
        return current

    async def _optional_live_properties(self, device):
        try:
            async with asyncio.timeout(5):
                response = await self._hms_request("control/deviceProperty", extra_params={
                    "boxId": device.box_id, "echonetNode": device.echonet_node,
                    "echonetObject": device.echonet_object, "status": "true",
                })
                return device_state(response, "deviceProperty", device)
        except SharpAuthError:
            raise
        except (SharpApiError, SharpConnectionError, TimeoutError):
            # A failed supplementary read must not discard valid deviceStatus.
            return None

    async def _confirm_power_after_error(self, device, expected, baseline):
        if baseline is None or state_timestamp(baseline[1]) is None:
            return False
        try:
            async with asyncio.timeout(12):
                for attempt in range(3):
                    if attempt:
                        await asyncio.sleep(2)
                    live = await self._optional_live_properties(device)
                    if (live is not None and live[0].power == expected
                            and at_least_as_recent(live[1], baseline[1], strictly=True)):
                        return True
        except TimeoutError:
            pass
        return False

    async def power_on(self, device):
        await self._set_power(device, True)

    async def power_off(self, device):
        await self._set_power(device, False)

    async def _set_power(self, device, on):
        expected = "on" if on else "off"
        record = {"requested_power": expected, "cloud_status": "unknown",
                  "state_confirmed": False, "outcome": "unconfirmed",
                  "requested_fields": ["80", "F3"]}
        self.last_power_commands[(device.box_id, device.device_id)] = record
        baseline = await self._optional_live_properties(device)
        try:
            # Life AIR 1.0.4 c6.a.m sends EPC 80 plus c6.h.q/t: F3 byte 14
            # with only bitmap bit 9 set. Restore the complete app payload;
            # the standard-only experiment did not resolve execution failures.
            # Send both fields in one POST, never an automatic fallback/retry.
            await self._send_device_control(device, [
                {"statusCode": "80", "valueType": "valueSingle",
                 "valueSingle": {"code": "30" if on else "31"}},
                f3_control(14, 0xFF if on else 0),
            ])
        except SharpCommandResultError as err:
            record.update(cloud_status=err.state, error_code=err.code)
            if err.state == "error" and err.code == "E1004003":
                record["state_confirmed"] = await self._confirm_power_after_error(device, expected, baseline)
                if record["state_confirmed"]:
                    record["outcome"] = "confirmed_by_state"
                    _LOGGER.warning("Sharp reported E1004003, but a newer deviceProperty state "
                                    "confirmed power %s; command was not repeated", expected)
                    return
            raise
        record.update(cloud_status="success", outcome="cloud_success")

    async def set_mode(self, device, mode):
        modes = {"auto": 0x10, "night": 0x11, "pollen": 0x13, "silent": 0x14,
                 "medium": 0x15, "high": 0x16, "ai_auto": 0x20, "realize": 0x40}
        if mode not in modes:
            raise ValueError("Unsupported Sharp operation mode")
        await self._send_device_control(device, [f3_control(5, modes[mode])])

    async def set_humidify(self, device, on):
        await self._send_device_control(device, [f3_control(16, 0xFF if on else 0)])

    async def _get_boxes(self):
        data = await super()._get_boxes()
        boxes = data.get("box") if isinstance(data, dict) else None
        if not isinstance(boxes, list) or any(
            not isinstance(box, dict) or not isinstance(box.get("boxId"), str)
            or not isinstance(box.get("echonetData", []), list) for box in boxes
        ):
            raise SharpApiError("setting/boxInfo: invalid box list")
        for box in boxes:
            for device in box.get("echonetData", []):
                device["echonetProperty"] = sanitize_properties(
                    device.get("echonetProperty")
                )
        return data

    async def _send_device_control(self, device, status_list):
        """Check acceptance and completion, following the official app sequence.

        A HTTP 200 is not sufficient: commands can be rejected in controlList,
        or remain waiting without ever reaching the purifier. Never resend the
        original POST automatically after an uncertain result.
        """
        await self._ensure_paired(device)
        response = await super()._send_device_control(device, status_list)
        fields = ",".join(sorted({str(item.get("statusCode", "")).upper()
                                  for item in status_list
                                  if re.fullmatch(r"[0-9A-Fa-f]{2}", str(item.get("statusCode", "")))}))
        controls = response.get("controlList") if isinstance(response, dict) else None
        if not isinstance(controls, list) or not controls:
            raise SharpApiError("deviceControl: invalid acknowledgement (" +
                                response_shape(response, "controlList") + ")")
        # The APK's acknowledgement decoder accepts a list, and its result
        # endpoint accepts a list of IDs. Do not impose a single-entry limit;
        # conservatively require completion of every ID returned by this POST.
        pending = {}
        for control in controls:
            if (not isinstance(control, dict) or "errorCode" not in control
                    or control.get("errorCode") not in (None, "null", "")):
                code = error_code(control.get("errorCode")) if isinstance(control, dict) else "unknown"
                raise SharpApiError(f"deviceControl: rejected command (errorCode={code})")
            command_id = command_identifier(control)
            identity = str(command_id)
            if identity in pending:
                raise SharpApiError("deviceControl: duplicate command identifiers")
            pending[identity] = command_id
        async with asyncio.timeout(30):
            await asyncio.sleep(2)
            while True:
                result = await self._hms_request(
                    "control/controlResult", method="POST",
                    body={"resultList": [{"id": command_id} for command_id in pending.values()]},
                    extra_params={"boxId": device.box_id},
                )
                results = result.get("resultList") if isinstance(result, dict) else None
                if not isinstance(results, list) or len(results) != len(pending):
                    raise SharpApiError("controlResult: invalid result (" +
                                        response_shape(result, "resultList") + ")")
                matched = {}
                for item in results:
                    identity = str(command_identifier(item, "controlResult"))
                    if identity not in pending or identity in matched:
                        raise SharpApiError("controlResult: mismatched command identifiers")
                    matched[identity] = item
                for identity, item in matched.items():
                    state = item.get("status")
                    if state == "success":
                        del pending[identity]
                    elif state == "unmatch":
                        raise SharpApiError("controlResult: unmatch; requested state was not confirmed")
                    elif state not in ("wait", "exec"):
                        raise SharpCommandResultError(state, item.get("errorCode"), fields)
                if not pending:
                    return response
                await asyncio.sleep(1)
