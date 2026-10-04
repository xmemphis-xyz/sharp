# Sharp Life AIR for Home Assistant

Experimental cloud integration for European Sharp Life AIR accounts, using
`aiosharp-cocoro-air==0.2.0`. Reading a KI-TX100EU has been confirmed with the
standalone test script. The user observed physical power-off on v0.1.9 despite
the cloud reporting E1004003. Other controls and v0.1.10 readback need physical
testing.

## Installation

For a public repository: HACS → three-dot menu → Custom repositories →
`https://github.com/xmemphis-xyz/sharp` → Integration. Download Sharp Life AIR
and restart Home Assistant.

For manual installation, copy `custom_components/sharp_life_air` into
`/config/custom_components/sharp_life_air` and restart Home Assistant.

Then Settings → Devices & services → Add Integration → Sharp Life AIR.
Use your Sharp Life AIR EU email and password. HA stores credentials in its
configuration storage; never commit them to GitHub.

## Entities

- Fan: power on/off, three manual speeds (Silent/Medium/High) and automatic presets.
- Select: Operation mode, with all eight API modes available on the device page.
- Switch: humidification for KI-series devices, even if the first response has empty state fields.
- Sensors: temperature, humidity, power, energy, airflow and operation modes.
- Diagnostic readings: raw dust, smell, filter, light and PCI values; no assumed
  units or percentages.
- Binary sensor: device fault.

Polling runs every 60 seconds. Discovery uses `setting/boxInfo`; current states
are then fetched through `control/deviceStatus`, matching the phone app.
Missing current fields are not filled from an older discovery snapshot.
Version 0.1.10 also requests `control/deviceProperty` with `status=true`, as the
official app does, when deviceStatus lacks control fields. Only a matching
device with a comparable timestamp at least as recent as deviceStatus can
supply readings. A failed supplementary read preserves valid deviceStatus data.
Version 0.1.6 handles decimal range readings larger than one byte and isolates
malformed optional status fields. Affected readings remain unknown; valid
readings from the same response remain available. Warnings identify the field
and value type without logging raw data.
Cloud readings may lag after commands. Available
modes are the library's modes; not all have been verified for KI-TX100EU.
The speed slider maps 1–33% to Silent, 34–66% to Medium, and 67–100% to High;
these percentages represent three selectable speeds, not measured fan output.
Setting the slider to zero turns the purifier off. Manual speeds are no longer
fan presets: use the speed slider or the Operation mode select for them.
Automatic modes keep the slider unknown rather than inventing a speed.

Commands follow the official app sequence: POST deviceControl, validate the
acknowledgement, then poll controlResult for up to 30 seconds. Rejected commands,
unmatched results and timeouts raise an HA action error. Uncertain writes are
never automatically repeated. For power commands only, an execution error
E1004003 can now be resolved by a readback of the requested EPC 80 state. HA
takes a deviceProperty/status=true baseline before the write, then makes up to
three readback requests within 12 seconds after this specific error. Confirmation
requires the exact device identity, explicit on/off value and a server timestamp
strictly newer than the baseline. A matching cached value, missing state,
unmatch or another error cannot authorize success. The original contradictory
cloud error is retained as a log warning and in diagnostics if state confirms.
Refresh immediately after completion and once
more after five seconds to accommodate cloud state delay. Physical-device
testing is still needed; a cloud result does not replace checking the purifier.
Version 0.1.7 accepts multiple acknowledgement entries and requires every
returned ID to complete. Malformed acknowledgements now identify the endpoint,
response/list type, entry count and a recognized protocol error code, without
logging raw data or identifiers. The reported KI-TX100EU failure did not expose
the actual response structure, so on-device confirmation is still required.
Power commands retain v0.1.8's standard EPC 80 payload. The user still received
`controlResult: status=error, errorCode=E1004003; fields=80` on that version, so
removing F3 did not resolve the reported failure. Its exact documented meaning
has not been established. Mode and humidification remain F3 controls.
If control fails or readings appear stale, use **Download diagnostics** from
the integration entry menu. It reads deviceProperty and deviceStatus and exports
only capability flags, known field types/presence/lengths, server update time,
registerLevel, numeric readings and pairing metadata. Pairing metadata includes
pairingFlag, maxFlag, pairedTerminalNum, whether this HA terminal is listed and
uses the EU app descriptor, and a valid box timezone. It omits configuration,
credentials, IDs, raw values and server messages. A timestamp without a timezone
is left unchanged.
Version 0.1.5 corrects the pinned library's F3 update masks for power, mode and
humidification using the Life AIR 1.0.4 APK. Failures now identify the endpoint
and cloud error code/status. An uncertain result also schedules a state refresh.
Energy is not yet enabled for Energy Dashboard totals because counter behavior
is unverified. No decoded PM2.5 concentration is provided by this library.

Version 0.1.9 fixes registration and pairing handling. Authentication keeps a
stable terminal identity in the existing HA config entry, including across
restart, setup retry and reauthentication. Registration uses the EU descriptor
from the Life AIR 1.0.4 app and rejects API errors in HTTP-success responses.
Before each deviceControl write, HA checks the current pairingFlag. If necessary
it requests pairing once and reads boxInfo again; a successful HTTP response
without confirmed pairing cannot authorize a device write. Pairing failures
during login are logged while valid sensor reads remain available.

The integration never automatically removes another terminal's registration.
If the server reports its terminal limit, it raises an explicit action error.
Keep the existing integration when updating; deleting it loses its saved identity.
The standalone test script still uses upstream authentication, which deletes
older HA registrations: avoid running it alongside the integration.

These are confirmed code defects, but their connection to E1004003 remains a
hypothesis. The user confirmed that v0.1.9 physically switched off the purifier
while reporting E1004003. Update in HACS, restart Home Assistant and test
power-off once. If it fails, send the action error and new diagnostics. Diagnostics
include the most recent power command's requested state, cloud outcome, protocol
error code and whether a newer device state confirmed it. They do not expose IDs
or raw data. If the readback cannot confirm power, the action error remains.

## First device test

Confirm readings, then test power off/on, Auto and humidification. Compare each
command against the physical purifier and Sharp app. Report HA errors with
credentials and device identifiers removed.

For experimental direct LAN connectivity use the independent
[Sharp Life AIR Local](https://github.com/xmemphis-xyz/sharp-local) integration.
It can coexist with this integration and requires no Sharp account.

## Development

```bash
python3 -m pip install aiosharp-cocoro-air==0.2.0
python3 -m unittest discover -s tests -v
```
