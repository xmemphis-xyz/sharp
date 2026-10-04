"""Sharp EU cloud adapter, matching the Life AIR 1.0.4 APK."""
import asyncio
import logging
import re
from dataclasses import replace

from aiosharp_cocoro_air import SharpCOCOROAir, SharpApiError, decode_echonet_property
from aiosharp_cocoro_air.models import DeviceProperties

_LOGGER = logging.getLogger(__name__)
_STATUS_CODES = {0x80, 0x84, 0x85, 0x88, 0x8B, 0xA0, 0xC0, 0xF1, 0xF3}


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

    async def _hms_request(self, path, *args, **kwargs):
        try:
            return await super()._hms_request(path, *args, **kwargs)
        except ValueError as err:
            raise SharpApiError(f"{path}: invalid JSON response") from err
        except SharpApiError as err:
            # Upstream embeds raw response text in errors, possibly with IDs.
            match = re.match(r"API error (\d{3}) on ", str(err))
            detail = f"HTTP {match[1]}" if match else "invalid API response"
            raise SharpApiError(f"{path}: {detail}") from err

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
            status = response.get("deviceStatus") if isinstance(response, dict) else None
            if not isinstance(status, dict):
                raise SharpApiError("deviceStatus: missing device status")
            if any(str(status.get(field)) != str(expected) for field, expected in (
                ("deviceId", device.device_id), ("echonetNode", device.echonet_node),
                ("echonetObject", device.echonet_object),
            )):
                raise SharpApiError("deviceStatus: mismatched device")
            # Do not fill missing readings with stale boxInfo values.
            current.append(replace(device, properties=decode_status(status.get("status")),
                                   updated_at=status.get("propertyUpdatedAt")))
        return current

    async def power_on(self, device):
        await self._set_power(device, True)

    async def power_off(self, device):
        await self._set_power(device, False)

    async def _set_power(self, device, on):
        await self._send_device_control(device, [
            {"statusCode": "80", "valueType": "valueSingle",
             "valueSingle": {"code": "30" if on else "31"}},
            f3_control(14, 0xFF if on else 0),
        ])

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
        for box in data.get("box", []):
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
        response = await super()._send_device_control(device, status_list)
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
                        raise SharpApiError(f"controlResult: status={error_code(state)}, "
                                            f"errorCode={error_code(item.get('errorCode'))}")
                if not pending:
                    return response
                await asyncio.sleep(1)
