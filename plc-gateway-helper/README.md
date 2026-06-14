# PLC Gateway Helper (read-only)

A **read-only** PLC telemetry helper for Factory Assistant. It polls explicitly
configured Modbus TCP input or holding registers, decodes their values, and
publishes telemetry to MQTT on the Factory Assistant topic convention
`fa/<site>/<area>/<device>/<measurement>`, with optional Home Assistant MQTT
discovery.

Factory Assistant is based on Home Assistant.

> ⚠️ **Safety boundary — read-only by construction.**
> This add-on uses Modbus read function codes 3 and 4 only. It does not write
> coils/registers, trigger machine actions, or connect to safety controllers.
> Configuration must keep `write_functions_allowed: false` and
> `safety_controller_allowed: false`; any other value refuses startup. Factory
> Assistant is a monitoring system, not a safety device. See the project safety
> boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/FactoryAssistantOS/blob/main/docs/SAFETY_BOUNDARY.md).

## What it does

- Connects to one Modbus TCP endpoint as a polling client.
- Reads configured holding registers (`function_code: 3`) or input registers
  (`function_code: 4`) on a fixed interval.
- Publishes each decoded value to `fa/<site>/<area>/<device>/<measurement>`.
- Emits MQTT discovery config so Factory Assistant creates matching sensors.

## What it deliberately does not do

- No coil writes, register writes, write functions, or MQTT command topics.
- No safety controller access.
- No host network, hardware access, Supervisor API, or Home Assistant API roles.
- Ships `boot: manual`; operators deliberately start it after confirming the
  read-only register list.

## Quick start

1. Install this add-on repository (see the repo `README.md`).
2. Install **PLC Gateway Helper (read-only)** and open its **Configuration**.
3. Set the Modbus endpoint, MQTT broker, `site`, and the `registers` list.
4. Start the add-on and confirm telemetry with an MQTT client subscribed to
   `fa/#`.

Full configuration reference: [`DOCS.md`](./DOCS.md).

## License

Apache-2.0 (see repository `LICENSE` / `NOTICE`). Bundles `paho-mqtt`
(EPL-2.0 / EDL-1.0) and `pymodbus` (BSD-3-Clause).
