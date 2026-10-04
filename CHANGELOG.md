# Changelog

## 0.1.7

- Remove the single-entry limit on deviceControl acknowledgements. Accept a
  nonempty list, validate every entry and confirm every returned command ID.
  Poll only the IDs still waiting; success requires all IDs to complete.
- Keep duplicate/malformed IDs, partial rejection, missing or unrelated results,
  unmatch and timeout as errors. Never repeat an uncertain deviceControl POST.
- Replace the generic "Invalid Sharp command acknowledgement" error with the
  endpoint and a safe description of the response structure. Include only a
  recognized top-level protocol errorCode, never raw response data or IDs.

38 regression tests pass. The reported error establishes that the old list
validation failed, but not whether controlList was absent, empty or had more
than one entry. Multiple-entry handling removes an unnecessary restriction;
the added diagnostics identify other response problems. Physical power-off
success still needs confirmation on KI-TX100EU.

## 0.1.6

- Fix the 0.1.5 deviceStatus parser's single-byte limit on decimal range
  values. Energy/power values above 255 now decode without raising ValueError.
- Parse each field independently. A malformed optional reading no longer
  prevents setup or discards valid power/humidity readings from the response.
- Handle null/empty codes and integer JSON single-value codes; ignore invalid
  fields with a warning identifying only the field and value type.
- Keep malformed top-level responses, mismatched device identity and responses
  containing only invalid fields as errors. Do not reuse cached sensor values.

29 regression tests pass. The user's screenshot identifies a parser failure,
but does not identify which raw field caused it. Physical testing is pending.

## 0.1.5

- Fix power, operation mode and humidification F3 update bitmaps to match
  the Sharp Life AIR 1.0.4 APK. The pinned library marked extra fields for
  update; the adapter now changes only the requested field.
- Read sensor/control states through control/deviceStatus, as the app does,
  instead of using the boxInfo discovery snapshot. Missing current readings
  remain unknown and are not replaced with older cached values.
- Include endpoint, command result status and errorCode in action errors;
  omit raw cloud response bodies and device identifiers.
- Refresh after uncertain command results without automatically repeating
  the command. Keep unmatch and timeout as failures, not confirmed success.

Validated with regression tests and APK command vectors. A physical test on
KI-TX100EU is still required; the reported failure's exact cloud code is
not available in the 0.1.4 log.

## 0.1.4

- Add an Operation mode select to the device's Controls section.
- Add a three-speed fan slider (Silent, Medium, High), with zero turning off.
- Separate manual speeds from automatic fan presets as required by HA.
- Create the humidification control for KI-series devices even when the
  initial cloud response contains no humidification state.
- Validate deviceControl acknowledgement and poll controlResult until success.
  Report rejection, unmatch, malformed replies or timeout as action errors;
  do not silently treat HTTP 200 as completed control or repeat uncertain writes.
- Serialize combined power/mode commands and refresh after cloud completion,
  with a follow-up refresh after five seconds.
- Preserve the 0.1.3 fix for empty ECHONET values.

KI-TX100EU cloud readings have been observed in the physical installation.
This update's commands require power/mode/humidification tests on that device.
