Sharp Life AIR 0.1.12 restores the complete power command used by the supplied official Life AIR 1.0.4 app.

Power on/off now sends EPC 80 together with F3 in one deviceControl POST. The F3 payload selects only byte 14 through bitmap bit 9; mode, humidification and other F3 settings are not selected for update. The exact payloads follow c6.a.m and c6.h.q/t in the APK. This replaces the standard-only experiment from 0.1.8–0.1.11, which did not resolve execution failures.

Stable HA terminal identity, confirmed pairing, current-state parsing and newer explicit power readback are retained. There is no automatic retry or alternative write after an error. Diagnostics include requested_fields [80, F3] for the last power command.

The latest supplied 0.1.11 diagnostics show paired=true, the current HA terminal listed, nine paired clients with maxFlag=true, E1004003 after power-off and null current power/F3 values. The user confirms the purifier did not physically switch off. These data do not identify E1004003's exact meaning or establish that the terminal limit is its cause. Missing power values still cannot confirm success; power consumption alone is never used to infer power state.

84 regression tests pass, including both official command vectors, unrelated F3 bytes, single-write behavior, pairing at the terminal limit, absent/stale/mismatched readback and allowlisted diagnostics. Device execution still requires physical verification. The full official payload previously appeared before the registration fixes from 0.1.9; this release combines them.

Update to 0.1.12 in HACS and restart Home Assistant. Keep the existing integration and test power-off once. Check physical operation. If it fails, send the new error and Download diagnostics after that attempt.

For manual installation, extract sharp_life_air.zip into /config.
