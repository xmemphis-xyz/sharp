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

- Fan: power on/off and API preset modes.
- Switch: humidification when the API reports support.
- Sensors: temperature, humidity, power, energy, airflow and operation modes.
- Diagnostic readings: raw dust, smell, filter, light and PCI values; no assumed
  units or percentages.
- Binary sensor: device fault.

Polling runs every 60 seconds. Cloud readings may lag after commands. Available
modes are the library's modes; not all have been verified for KI-TX100EU.
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
