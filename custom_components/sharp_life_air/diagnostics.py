"""Allowlisted cloud diagnostics, without credentials or device identifiers."""
import asyncio
import re

_CODES = {"80", "84", "85", "86", "88", "8B", "A0", "C0", "F1", "F2", "F3", "FD"}
_TYPES = {"valueSingle", "valueRange", "valueBinary"}


def summarize(response, field, device):
    """Keep capability flags, payload lengths and timestamps, never raw values."""
    data = response.get(field) if isinstance(response, dict) else None
    if not isinstance(data, dict):
        return {"available": False}
    matches = all(str(data.get(key)) == str(expected) for key, expected in (
        ("deviceId", device.device_id), ("echonetNode", device.echonet_node),
        ("echonetObject", device.echonet_object),
    ))
    result = {"available": True, "identity_matches": matches}
    if not matches:
        return result
    timestamp = data.get("propertyUpdatedAt")
    if isinstance(timestamp, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", timestamp
    ):
        result["property_updated_at"] = timestamp
    items = data.get("property" if field == "deviceProperty" else "status")
    if not isinstance(items, list):
        result["fields_available"] = False
        return result
    result["fields"] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = item.get("statusCode")
        if not isinstance(code, str) or code.upper() not in _CODES:
            continue
        info = {"code": code.upper()}
        kind = item.get("valueType")
        if isinstance(kind, str) and kind in _TYPES:
            info["value_type"] = kind
        for flag in ("get", "set", "inf"):
            if type(item.get(flag)) is bool:
                info[flag] = item[flag]
        value = item.get(kind) if isinstance(kind, str) and kind in _TYPES else None
        if isinstance(value, dict):
            value = value.get("code")
            info["has_value"] = value not in (None, "", "null")
            if kind == "valueBinary" and isinstance(value, str) and re.fullmatch(r"(?:[0-9A-Fa-f]{2}){0,255}", value):
                info["payload_bytes"] = len(value) // 2
        result["fields"].append(info)
    return result


async def async_get_config_entry_diagnostics(hass, entry):
    """Read the two official metadata endpoints when diagnostics are requested."""
    coordinator = entry.runtime_data
    result = {"last_update_success": coordinator.last_update_success, "devices": []}
    async with coordinator.lock:
        for device in (coordinator.data or {}).values():
            record = {}
            for field in ("humidity_pct", "temperature_c", "power_watts"):
                value = getattr(device.properties, field, None)
                record[field] = value if type(value) in (int, float) else None
            for endpoint, field in (("control/deviceProperty", "deviceProperty"),
                                    ("control/deviceStatus", "deviceStatus")):
                try:
                    async with asyncio.timeout(5):
                        response = await coordinator.client._hms_request(
                            endpoint, extra_params={"boxId": device.box_id,
                            "echonetNode": device.echonet_node,
                            "echonetObject": device.echonet_object},
                        )
                    record[field] = summarize(response, field, device)
                except Exception as err:
                    # Exception messages can contain URLs or authentication data.
                    record[field] = {"available": False, "error_type": type(err).__name__}
            result["devices"].append(record)
    return result
