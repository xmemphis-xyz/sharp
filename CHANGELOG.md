# Changelog

## 0.1.10

- Request deviceProperty with status=true, matching Life AIR 1.0.4. Supplement
  missing controls/readings only from the exact device with a comparable server
  timestamp at least as recent as deviceStatus. Preserve valid deviceStatus
  readings if the supplementary endpoint fails.
- For power-only E1004003 execution errors, read back the desired EPC 80 state.
  Require exact identity, explicit on/off and a timestamp strictly newer than
  the pre-write deviceProperty baseline. Read up to three times within 12 seconds;
  never resend deviceControl. Unknown, unchanged/stale, mismatched states, other
  errors and unmatch remain failures.
- Include allowlisted last-power-command outcome in diagnostics and use
  status=true for its deviceProperty read. Retain a warning about E1004003 when
  the state confirms success; never silently discard the cloud error.

80 tests pass, including full local HTTP readback scenarios. The user reports
that v0.1.9 physically switched the purifier off despite E1004003. The new live
read and readback mechanism need physical verification; if the cloud continues
to omit EPC 80, this version cannot confirm power and retains the action error.
The exact documented meaning of E1004003 is still unknown.

## 0.1.9

- Retain terminalAppId in the HA config entry across startup, setup retry and
  reauthentication. Reuse the identity tested in the initial config flow.
- Register with the EU app descriptor from Life AIR 1.0.4. Validate HTTP-success
  JSON errorCode responses for registration, pairing and ordinary API calls.
- Stop upstream's automatic deletion of other terminal registrations. Report
  pairing failures and terminal limits explicitly, preserving valid sensor reads.
- Check fresh pairingFlag before device writes. When pairing is needed, request
  it once and require a successful readback before sending deviceControl.
  Command result validation and no automatic control-write retries are retained.
- Add registration flags, bounded terminal count, current-client membership,
  descriptor match, registerLevel and validated timezone to private-data-free
  diagnostics. Diagnostics only read metadata; they never register or pair.

67 tests pass, including local HTTP protocol tests and integration storage tests
with HA interface doubles. Physical KI-TX100EU control is not yet verified.
The user still receives E1004003 with v0.1.8's EPC 80-only power command; removing
F3 did not fix it. Registration defects are now fixed, but neither their role
in this failure nor the exact meaning of E1004003 has been established.

## 0.1.8

- Use only the standard EPC 80 operation-status field for power on/off. Remove
  the additional proprietary F3 field from power requests, while preserving
  confirmation polling and the prohibition on automatic write retries.
- Include the requested field codes in execution errors (e.g. `fields=80`).
- Add Download diagnostics with allowlisted deviceProperty capabilities and
  deviceStatus field presence/lengths and the server's update timestamp. These
  two reads run only when diagnostics are requested, serialized with commands
  and individually bounded to five seconds. No credentials, raw payloads,
  device/command IDs or arbitrary server messages are exported.

44 tests pass. The physical test on 0.1.7 now reaches controlResult and returns
`status=error, errorCode=E1004003`. Its exact documented meaning is unknown.
Removing the supplementary F3 command tests a possible compatibility issue;
successful operation on KI-TX100EU remains unconfirmed. Diagnostic timestamps
are preserved as returned, without assuming a timezone for naive values.

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
