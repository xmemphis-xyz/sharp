"""Sharp EU cloud adapter, matching the Life AIR 1.0.4 APK."""
import asyncio
import re
from dataclasses import replace

from aiosharp_cocoro_air import SharpCOCOROAir, SharpApiError, decode_echonet_property
from aiosharp_cocoro_air.models import DeviceProperties


def error_code(value):
    """Expose only bounded protocol codes, never arbitrary server messages."""
    code = str(value)
    return code if re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code) else "unknown"


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
    """Convert deviceStatus.status to the pinned decoder's TLV format."""
    if not isinstance(status, list):
        raise SharpApiError("deviceStatus: missing status list")
    data = bytearray(8)
    for item in status:
        try:
            code = int(item["statusCode"], 16)
            if code not in {0x80, 0x84, 0x85, 0x88, 0x8B, 0xA0, 0xC0, 0xF1, 0xF3}:
                continue
            kind = item["valueType"]
            if kind not in {"valueSingle", "valueRange", "valueBinary"}:
                raise ValueError("Unknown value type")
            value = item[kind]["code"]
            if value in (None, ""):
                continue
            # Range values use decimal text; single/binary values use hex.
            payload = bytes([int(value)]) if kind == "valueRange" else bytes.fromhex(value)
            if payload:
                data.extend(bytes([code, len(payload)]))
                data.extend(payload)
        except (KeyError, TypeError, ValueError, OverflowError) as err:
            raise SharpApiError("deviceStatus: invalid status value") from err
    try:
        return DeviceProperties(**decode_echonet_property(data.hex()))
    except (IndexError, TypeError, ValueError) as err:
        raise SharpApiError("deviceStatus: invalid property data") from err


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
        if not isinstance(controls, list) or len(controls) != 1:
            raise SharpApiError("Invalid Sharp command acknowledgement")
        control = controls[0]
        if (not isinstance(control, dict) or "errorCode" not in control
                or control.get("errorCode") not in (None, "null", "")):
            code = error_code(control.get("errorCode")) if isinstance(control, dict) else "unknown"
            raise SharpApiError(f"deviceControl: rejected command (errorCode={code})")
        command_id = control.get("id")
        if not command_id:
            raise SharpApiError("Sharp did not return a command identifier")
        async with asyncio.timeout(30):
            await asyncio.sleep(2)
            while True:
                result = await self._hms_request(
                    "control/controlResult", method="POST",
                    body={"resultList": [{"id": command_id}]},
                    extra_params={"boxId": device.box_id},
                )
                results = result.get("resultList") if isinstance(result, dict) else None
                if not isinstance(results, list) or len(results) != 1:
                    raise SharpApiError("Invalid Sharp command result")
                item = results[0]
                if not isinstance(item, dict) or str(item.get("id")) != str(command_id):
                    raise SharpApiError("Mismatched Sharp command result")
                state = item.get("status")
                if state == "success":
                    return response
                if state == "unmatch":
                    raise SharpApiError("controlResult: unmatch; requested state was not confirmed")
                if state not in ("wait", "exec"):
                    raise SharpApiError(f"controlResult: status={error_code(state)}, "
                                        f"errorCode={error_code(item.get('errorCode'))}")
                await asyncio.sleep(1)
