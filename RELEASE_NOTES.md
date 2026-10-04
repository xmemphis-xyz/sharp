Sharp Life AIR 0.1.11 fixes an incorrect current-state parser introduced in 0.1.10.

The user's log showed repeated invalid 8B/A0/C0/F1/F3 warnings. The deviceProperty response contains separate property and status sections: property holds capabilities, enum choices, ranges and binary schemas; status holds current readings. Version 0.1.10 mistakenly decoded property as current state. The correct separation is established by b6.l.f.c in the supplied Life AIR 1.0.4 APK.

The integration now decodes only deviceProperty.status for supplementary readings, pre-write baselines and power readback. Capability-only responses cannot supply or confirm power. Actual malformed status values still produce the existing bounded field/type warnings. The reported warnings caused by interpreting definitions as readings are fixed without suppressing genuine malformed values.

Download diagnostics retains property capability flags and adds a separate current_status summary of embedded live values. Raw values, definitions, terminal/device/command IDs, account data and server messages remain omitted.

Power payload and confirmation rules are unchanged. One standard EPC 80 control write is sent. After E1004003, power can be confirmed only by the exact device's explicit requested state and a timestamp strictly newer than the baseline, using up to three readbacks within 12 seconds. Missing/stale/mismatched states and other errors remain failures. No automatic repeat or alternate control payload is introduced.

The user observed physical power-off and delayed power-on before this fix. The latest HA screenshot displays power, auto mode and humidification, but also E1004003 after power-off. The new parser/readback must still be verified on the physical purifier; this release does not establish the exact meaning of E1004003 or guarantee that all delayed commands will complete within its confirmation window.

Update to 0.1.11 in HACS and restart Home Assistant. Keep the existing integration. Test power-off once, check the physical purifier and send new Download diagnostics if an error remains. This file contains the most recent power-command outcome and embedded current-state field availability.

83 regression tests pass. HTTP fixtures now accurately include both capability and current-state sections. Added tests confirm that schemas cannot be decoded or used to verify power and that diagnostics distinguish the two sections without exposing private data. Tests do not replace physical verification.

For manual installation, extract sharp_life_air.zip into /config.
