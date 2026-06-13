# OPC UA → MQTT Bridge (read-only)

A **read-only** OPC UA to MQTT bridge for Factory Assistant. It subscribes to a
curated set of OPC UA server nodes, reads their values, and republishes them to
MQTT on the Factory Assistant topic convention
`fa/<site>/<area>/<device>/<measurement>`, with optional Home Assistant MQTT
discovery so entities are created automatically.

Factory Assistant is based on Home Assistant.

> ⚠️ **Safety boundary — read-only by construction.**
> This add-on **subscribes to and reads** OPC UA nodes only. It **never writes**
> to an OPC UA server: there is no write path in the code, and a startup
> self-check refuses to run if one is ever introduced. Writing to an OPC UA
> node is a machine-control path and is **prohibited** by the Factory Assistant
> safety boundary. Factory Assistant is a monitoring system, not a safety
> device, and must never implement machine control, e-stop, interlocks, or any
> safety-rated function. See the project safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/factory-assistant/blob/main/docs/SAFETY_BOUNDARY.md).

## What it does

- Connects to one OPC UA endpoint (read-only client).
- Reads each configured node on a fixed interval (an OPC UA *Read* service).
- Publishes each value to `fa/<site>/<area>/<device>/<measurement>` (QoS 1),
  plus a retained `…/status` availability topic per device.
- Emits HA MQTT discovery config (retained) so Factory Assistant creates the
  matching `sensor.<area>_<device>_<measurement>` entities automatically.

## What it deliberately does not do

- No OPC UA writes, method calls, or attribute writes.
- No MQTT command topics, no subscriptions that act on a device.
- No host network, no hardware access, no Supervisor/Home Assistant API roles.

## Quick start

1. Install this add-on repository (see the repo `README.md`).
2. Install **OPC UA → MQTT Bridge (read-only)** and open its **Configuration**.
3. Set the OPC UA `endpoint`, your MQTT broker (defaults target the Mosquitto
   add-on at `core-mosquitto`), `site`, and the `nodes` list (one entry per
   measurement — see `DOCS.md` for the schema).
4. Start the add-on. With discovery enabled, entities appear automatically;
   confirm topics with an MQTT client subscribed to `fa/#`.

Full configuration reference: [`DOCS.md`](./DOCS.md).

## License

Apache-2.0 (see repository `LICENSE` / `NOTICE`). Bundles `asyncua` (LGPL-3.0),
`paho-mqtt` (EPL-2.0 / EDL-1.0), and `PyYAML` (MIT).
