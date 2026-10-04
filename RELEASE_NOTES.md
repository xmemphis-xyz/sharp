Sharp Life AIR 0.1.5 corrects cloud command payloads and state retrieval.

Power, operation mode and humidification now use the F3 update masks from the
official Life AIR 1.0.4 APK. The pinned library's commands marked additional
fields for update. Readings now use control/deviceStatus instead of the cached
setting/boxInfo discovery snapshot. Missing current fields stay unknown.

Command errors show the endpoint and cloud error code/status, without raw
response bodies or device IDs. Failed or uncertain commands trigger a state
refresh but are never automatically resent. Unmatch and timeout still raise
errors because they do not confirm the requested device state.

Install/update with HACS, then restart Home Assistant. Existing configuration
and entity IDs are retained. Check humidity against the Sharp app and purifier,
then test power off/on, Auto and Humidification. If an action still fails, send
the new Sharp command error containing deviceControl or controlResult.

Regression tests and APK command vectors pass. Physical-device operation and
the root cause of the reported 0.1.4 command failure remain to be confirmed.

For manual installation, extract sharp_life_air.zip into /config.
