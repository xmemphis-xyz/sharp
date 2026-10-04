"""Handle empty ECHONET values returned by the Sharp EU cloud."""
import asyncio

from aiosharp_cocoro_air import SharpCOCOROAir, SharpApiError


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
            raise SharpApiError("Sharp rejected the command")
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
                    raise SharpApiError("Sharp executed the command but the requested state was not confirmed")
                if state not in ("wait", "exec"):
                    raise SharpApiError("Sharp command did not complete successfully")
                await asyncio.sleep(1)
