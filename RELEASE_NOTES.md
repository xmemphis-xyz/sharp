Sharp Life AIR 0.1.6 fixes deviceStatus parsing after the 0.1.5 update.

Decimal valueRange readings above 255 are now supported. Null/empty codes and
integer JSON single-value codes are handled. Each field is decoded separately,
so a malformed optional field no longer blocks setup or discards other valid
readings. An invalid field stays unknown and produces a warning with its field
code and value type, without raw data or device/account identifiers.

Malformed top-level responses, mismatched device identity and replies containing
only invalid fields still fail rather than presenting cached data as current.
The command-mask corrections and deviceStatus retrieval from 0.1.5 are retained.

Update to 0.1.6 in HACS and restart Home Assistant. Keep the existing integration
configuration. Check that setup completes, compare humidity with the purifier,
and test power and humidification. If fields remain unknown, send warnings
beginning with deviceStatus: ignored invalid field. For control failures send
the command error containing deviceControl or controlResult.

29 regression tests pass. The reported screenshot confirms a parser error but
does not identify the exact raw field. Operation on the physical purifier still
needs confirmation.

For manual installation, extract sharp_life_air.zip into /config.
