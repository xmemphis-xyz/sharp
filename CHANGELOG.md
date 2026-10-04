# Changelog

## 0.1.4

- Add an Operation mode select to the device's Controls section.
- Add a three-speed fan slider (Silent, Medium, High), with zero turning off.
- Separate manual speeds from automatic fan presets as required by HA.
- Create the humidification control for KI-series devices even when the
  initial cloud response contains no humidification state.
- Validate deviceControl acknowledgement and poll controlResult until success.
  Report rejection, unmatch, malformed replies or timeout as action errors;
  do not silently treat HTTP 200 as completed control or repeat uncertain writes.
- Serialize combined power/mode commands and refresh after cloud completion,
  with a follow-up refresh after five seconds.
- Preserve the 0.1.3 fix for empty ECHONET values.

KI-TX100EU cloud readings have been observed in the physical installation.
This update's commands require power/mode/humidification tests on that device.
