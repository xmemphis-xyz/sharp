# Sharp Life AIR for Home Assistant

Experimental cloud integration for European Sharp Life AIR accounts, using
`aiosharp-cocoro-air==0.2.0`. Reading a KI-TX100EU has been confirmed with the
standalone test script. Commands and this HA component still need testing on
the device.

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
never automatically repeated. Refresh immediately after completion and once
more after five seconds to accommodate cloud state delay. Physical-device
testing is still needed; a cloud result does not replace checking the purifier.
Version 0.1.7 accepts multiple acknowledgement entries and requires every
returned ID to complete. Malformed acknowledgements now identify the endpoint,
response/list type, entry count and a recognized protocol error code, without
logging raw data or identifiers. The reported KI-TX100EU failure did not expose
the actual response structure, so on-device confirmation is still required.
Version 0.1.5 corrects the pinned library's F3 update masks for power, mode and
humidification using the Life AIR 1.0.4 APK. Failures now identify the endpoint
and cloud error code/status. An uncertain result also schedules a state refresh.
Energy is not yet enabled for Energy Dashboard totals because counter behavior
is unverified. No decoded PM2.5 concentration is provided by this library.

Authentication registers a Home Assistant terminal with Sharp. The upstream
library cleans up older Home Assistant terminal registrations, so avoid running
the standalone test concurrently with the integration or multiple HA instances
on the same Sharp account.

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
