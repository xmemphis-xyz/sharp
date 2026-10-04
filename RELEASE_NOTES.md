Sharp Life AIR 0.1.10 adds live-state reads and power readback for the reported contradictory cloud error.

The user confirmed that v0.1.9 physically turned the KI-TX100EU off, while HA showed controlResult: status=error, errorCode=E1004003; fields=80. This confirms that the command can reach the purifier, but does not establish the error code's documented meaning or confirm other controls.

The official Life AIR 1.0.4 app requests deviceProperty with status=true. HA now uses this read when deviceStatus lacks control fields, accepting supplementary readings only for the exact device with a comparable timestamp at least as recent as deviceStatus. Diagnostics use the same live read. A failed supplementary read preserves valid sensor data.

Before a power command, HA captures a live deviceProperty baseline. If the matched command result then reports precisely status=error and E1004003, HA reads power back up to three times within 12 seconds. Only explicit EPC 80 on/off matching the requested state, for the exact device and with a timestamp strictly newer than the baseline, resolves the action as confirmed by state. The original cloud error remains in a log warning and diagnostics.

Missing state, stale/unchanged timestamps, mismatched identity, another error code and unmatch remain failures. This is not blanket suppression of E1004003, and no deviceControl write is repeated or sent with another payload. Power retains the standard-only EPC 80 command that the user observed switching the device off. Mode and humidification behavior are unchanged.

Download diagnostics includes the last power command's requested state, cloud status/error code, state confirmation and final outcome. It omits identities, credentials, raw values and messages and performs no registration or control writes.

Update to 0.1.10 in HACS, restart Home Assistant and keep the existing integration. Test power-off once and check the physical purifier and HA state. If an error remains, send the new Download diagnostics, which now contains the power command outcome. The live read and readback still need verification on the physical device. If Sharp continues to omit power state, the integration will retain the action error rather than assume success from low wattage or missing data.

80 regression tests pass, including real local HTTP tests for power on/off with contradictory execution results, exact-device and timestamp checks, genuine failure preservation and single-write behavior. Tests do not replace physical-device verification.

For manual installation, extract sharp_life_air.zip into /config.
