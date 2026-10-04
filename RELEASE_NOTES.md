Sharp Life AIR 0.1.9 fixes client registration and pairing handling for HA control.

The integration now retains terminalAppId in the existing config entry across restart, setup retry and reauthentication. Initial setup and subsequent operation use the same identity. Previously the dependency allocated a new identity on every login, ignored pairing failures and deleted other HA or unnamed terminal registrations.

Registration uses the EU descriptor from the Life AIR 1.0.4 app. Registration, pairing and ordinary API calls reject top-level errorCode responses even when HTTP succeeds. No other terminal registrations are automatically removed. Pairing failures during login are reported while valid sensor reads remain available.

Before each deviceControl write, HA reads current pairingFlag. If unpaired, it requests pairing once and reads boxInfo again. If pairing is rejected, the terminal limit is reached or readback does not confirm pairing, no device command is sent. Accepted device commands still require matching successful controlResult entries. Uncertain control writes are never repeated automatically.

Download diagnostics now includes pairing flags, bounded terminal count, whether the current HA terminal is listed with the EU descriptor, registerLevel and validated box timezone. It still omits credentials, config data, terminal/device/command IDs, names, raw payloads and arbitrary server messages. Downloading diagnostics performs reads only.

The reported v0.1.8 error remains controlResult: status=error, errorCode=E1004003; fields=80. Removing F3 did not fix it. These registration defects are confirmed in code, but their role in E1004003 is not confirmed. The error code's exact documented meaning is unknown, and physical-device control still requires testing.

Update to 0.1.9 in HACS and restart Home Assistant. Keep the existing integration; it will save its terminal identity automatically. Try power-off once and check the physical purifier. If it fails, send the complete action error and new Download diagnostics from Settings > Devices & services > Sharp Life AIR > integration entry menu.

67 regression tests pass. Local HTTP tests cover stable identity, registration and pairing rejection, terminal limits, readback, control completion and no repeated device writes. Identity-storage tests exercise flow/coordinator code with small HA interface doubles; they are not a full HA runtime or physical-device test.

For manual installation, extract sharp_life_air.zip into /config.
