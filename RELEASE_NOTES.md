Sharp Life AIR 0.1.8 simplifies power commands and adds cloud capability/freshness diagnostics for the KI-TX100EU control failure.

Power on/off now sends only standard EPC 80, code 30/31, instead of combining it with the proprietary F3 power field. Command acknowledgement and result validation remain mandatory. An execution error identifies the requested field codes. Uncertain writes are never automatically repeated.

The reported 0.1.7 error is controlResult: status=error, errorCode=E1004003. The code's exact documented meaning has not been established. Removing the supplementary F3 command tests a possible compatibility issue; this is not a confirmed device fix. Mode and humidification controls remain unchanged and require physical verification.

Download diagnostics is now available in the integration entry menu. When requested, it reads deviceProperty and deviceStatus with a five-second timeout per request. The output includes known field capabilities, presence and byte lengths, server update timestamps and numeric humidity/temperature/power readings. Credentials, configuration, identifiers, raw cloud payloads and arbitrary error messages are omitted. Naive server timestamps are not assigned an assumed timezone.

Update to 0.1.8 in HACS and restart Home Assistant. Keep the existing integration configuration. Try power-off once and check the physical purifier. If it still fails, send the new command error and Download diagnostics from Settings > Devices & services > Sharp Life AIR > the integration entry menu. The diagnostics also help investigate the remaining 50% humidity reading and unknown operation mode.

44 regression tests pass, covering standard-only power requests, the observed E1004003 execution failure, acknowledgement/result validation, no automatic retries, status parsing and diagnostic privacy. Device operation remains to be confirmed.

For manual installation, extract sharp_life_air.zip into /config.
