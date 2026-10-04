Sharp Life AIR 0.1.4 adds an Operation mode select, a three-speed fan slider (Silent/Medium/High), and humidification for KI devices even when the initial reading is empty.

Commands validate the cloud acknowledgement and poll the official controlResult endpoint. Rejection, mismatched results or timeout produce an HA action error. Uncertain commands are not automatically repeated. State refreshes immediately and after five seconds.

Install/update using HACS, then restart Home Assistant. Existing configuration is retained. On the device page, test power off/on, Auto, the speed slider and Humidification against the physical purifier.

Cloud readings have been observed on KI-TX100EU. Automated tests pass, but these updated control commands still need a physical-device test. Manual fan speeds are now represented by the speed slider or Operation mode select instead of fan presets.

For manual installation, extract sharp_life_air.zip into /config.
