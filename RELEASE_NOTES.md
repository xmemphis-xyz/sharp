Sharp Life AIR 0.1.7 removes a restrictive command acknowledgement check and adds safe diagnostics for the reported fan.turn_off failure.

Previously, the adapter required exactly one controlList entry and otherwise raised "Invalid Sharp command acknowledgement". The APK acknowledgement decoder accepts a list, and controlResult accepts a list of command IDs. The adapter now validates all returned entries and polls every accepted ID, reporting success only after all complete. IDs already confirmed are removed from subsequent polling.

Partial rejection, duplicate or malformed IDs, missing or unrelated results, unmatch and timeout remain failures. The original command POST is never automatically repeated. State is refreshed after uncertain outcomes.

If an acknowledgement is still invalid, the error now includes deviceControl, the response type, the known list field's type/count and a recognized top-level protocol errorCode when present. No raw cloud payloads, tokens or device/command identifiers are included.

Update to 0.1.7 in HACS, restart Home Assistant, keep the existing configuration and try turning the purifier off once. Confirm the physical device turns off. If it fails, send the full new error beginning with deviceControl or controlResult.

38 regression tests pass, including multiple acknowledgements, mixed success/wait/error, duplicate/missing/unrelated IDs, partial-success timeout and diagnostic privacy. The user's log proves the previous acknowledgement validation failed but does not reveal the response structure. Multiple entries are a possible cause; physical testing is still required.

For manual installation, extract sharp_life_air.zip into /config.
