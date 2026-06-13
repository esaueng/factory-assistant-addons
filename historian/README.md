# Historian (telemetry → TSDB)

Long-term telemetry exporter for Factory Assistant. It **reads** measurements
from MQTT (the `fa/#` topic tree published by the appliance and by the OPC UA
bridge) and **writes** them to a time-series database (InfluxDB, with a
documented TimescaleDB path) for trending, retention, and analytics beyond the
on-box recorder window.

Factory Assistant is based on Home Assistant.

> ⚠️ **Safety boundary — monitoring/archival only.**
> This add-on reads telemetry and writes it to a **database**. A database write
> is data archival, **not** a machine-control path. This add-on never writes to
> a PLC, OPC UA server, fieldbus, or any machine I/O. Factory Assistant is a
> monitoring system, not a safety device, and must never implement machine
> control, e-stop, interlocks, or any safety-rated function. See the project
> safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/factory-assistant/blob/main/docs/SAFETY_BOUNDARY.md).

## What it does

- Subscribes to a configurable MQTT topic filter (default `fa/#`).
- Parses numeric payloads (raw numbers or flat JSON like `{"value": 58.2}`).
- Writes each value to InfluxDB via the line-protocol HTTP write API, tagged
  by `site` / `area` / `device` / `metric` derived from the topic.

## What it does not do

- No machine/PLC/OPC UA writes; no MQTT command topics.
- No host network, no hardware access, no Supervisor/HA API roles.

## Quick start (InfluxDB)

1. Install an InfluxDB add-on (e.g. the community InfluxDB add-on) or point at
   an external InfluxDB 2.x instance; create an org, bucket, and API token.
2. Install this add-on, open **Configuration**, set `tsdb.url`, `influx_org`,
   `influx_bucket`, and `influx_token`, and confirm the MQTT source.
3. Start the add-on; query the `fa_telemetry` measurement in InfluxDB.

Full reference and the Telegraf/TimescaleDB alternative:
[`DOCS.md`](./DOCS.md).

## Status / honesty

The bundled Python exporter is a **thin but working** MQTT→InfluxDB path
(numeric values only). For production-grade ingestion (string states, batching,
backpressure, TimescaleDB) the recommended path is **Telegraf** with the
`mqtt_consumer` input, documented in `DOCS.md`.

## License

Apache-2.0 (see repository `LICENSE` / `NOTICE`). Bundles `paho-mqtt`
(EPL-2.0 / EDL-1.0); the InfluxDB write path uses only the Python standard
library.
