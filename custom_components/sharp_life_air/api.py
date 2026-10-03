"""Handle empty ECHONET values returned by the Sharp EU cloud."""
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
