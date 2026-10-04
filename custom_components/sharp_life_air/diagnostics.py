"""Allowlisted cloud diagnostics, without credentials or device identifiers."""
import asyncio
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    level = data.get("registerLevel")
    if type(level) is int and 0 <= level <= 255:
        result["register_level"] = level
    timestamp = data.get("propertyUpdatedAt")
    if isinstance(timestamp, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?", timestamp
    ):
        result["property_updated_at"] = timestamp
    if field == "deviceProperty":
        result["current_status"] = summarize({"deviceStatus": data}, "deviceStatus", device)
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
        if field == "deviceStatus" and isinstance(value, dict):
            value = value.get("code")
            info["has_value"] = value not in (None, "", "null")
            if kind == "valueBinary" and isinstance(value, str) and re.fullmatch(r"(?:[0-9A-Fa-f]{2}){0,255}", value):
                info["payload_bytes"] = len(value) // 2
        result["fields"].append(info)
    return result


def summarize_box(response, device, client):
    """Expose pairing state for this client, never other terminal identities."""
    boxes = response.get("box") if isinstance(response, dict) else None
    if not isinstance(boxes, list):
        return {"available": False}
    box = next((box for box in boxes if isinstance(box, dict)
                and box.get("boxId") == device.box_id), None)
    if box is None:
        return {"available": False}
    result = {"available": True}
    for source, target in (("pairingFlag", "paired"), ("maxFlag", "terminal_limit_reached")):
        if type(box.get(source)) is bool:
            result[target] = box[source]
    count = box.get("pairedTerminalNum")
    if type(count) is int and 0 <= count <= 1000:
        result["paired_terminal_count"] = count
    terminals = box.get("terminalAppInfo")
    identity = getattr(client, "terminal_app_id", None)
    if isinstance(terminals, list) and identity:
        current = next((terminal for terminal in terminals if isinstance(terminal, dict)
                        and terminal.get("terminalAppId") == identity), None)
        result["current_terminal_listed"] = current is not None
        if current is not None:
            result["current_terminal_uses_eu_app_descriptor"] = (
                isinstance(current.get("appName"), str)
                and current["appName"].startswith("spremote_a_eu:")
            )
    result["pairing_failed_during_login"] = device.box_id in getattr(client, "_pairing_errors", {})
    timezone = box.get("timezone")
    if isinstance(timezone, str) and len(timezone) <= 64:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            pass
        else:
            result["box_timezone"] = timezone
    return result


async def async_get_config_entry_diagnostics(hass, entry):
    """Read official pairing and metadata endpoints on diagnostic requests."""
    coordinator = entry.runtime_data
    result = {"last_update_success": coordinator.last_update_success, "devices": []}
    async with coordinator.lock:
        try:
            async with asyncio.timeout(5):
                boxes = await coordinator.client._hms_request(
                    "setting/boxInfo", extra_params={"mode": "other"},
                )
            box_error = None
        except Exception as err:
            boxes = None
            box_error = {"available": False, "error_type": type(err).__name__}
        for device in (coordinator.data or {}).values():
            # Timezone validation can read the system timezone database.
            registration = box_error if box_error is not None else await asyncio.to_thread(
                summarize_box, boxes, device, coordinator.client,
            )
            record = {"registration": registration}
            latest = getattr(coordinator.client, "last_power_commands", {}).get(
                (device.box_id, getattr(device, "device_id", None)),
            )
            if isinstance(latest, dict):
                command = {}
                for key, choices in (
                    ("requested_power", {"on", "off"}),
                    ("cloud_status", {"unknown", "success", "error", "wait", "exec"}),
                    ("outcome", {"unconfirmed", "cloud_success", "confirmed_by_state"}),
                ):
                    if isinstance(latest.get(key), str) and latest[key] in choices:
                        command[key] = latest[key]
                if type(latest.get("state_confirmed")) is bool:
                    command["state_confirmed"] = latest["state_confirmed"]
                code = latest.get("error_code")
                if isinstance(code, str) and re.fullmatch(r"E\d{7}", code):
                    command["error_code"] = code
                record["last_power_command"] = command
            for field in ("humidity_pct", "temperature_c", "power_watts"):
                value = getattr(device.properties, field, None)
                record[field] = value if type(value) in (int, float) else None
            for endpoint, field in (("control/deviceProperty", "deviceProperty"),
                                    ("control/deviceStatus", "deviceStatus")):
                try:
                    async with asyncio.timeout(5):
                        params = {"boxId": device.box_id,
                            "echonetNode": device.echonet_node,
                            "echonetObject": device.echonet_object}
                        if field == "deviceProperty":
                            params["status"] = "true"
                        response = await coordinator.client._hms_request(endpoint, extra_params=params)
                    record[field] = summarize(response, field, device)
                except Exception as err:
                    # Exception messages can contain URLs or authentication data.
                    record[field] = {"available": False, "error_type": type(err).__name__}
            result["devices"].append(record)
    return result
