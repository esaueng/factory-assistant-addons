# Historian Storage — configuration

Factory Assistant is based on Home Assistant.

> ⚠️ **Monitoring/archival only.** Reads MQTT telemetry, writes to a time-series
> database. No machine-control path. See the Factory Assistant safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/FactoryAssistantOS/blob/main/docs/SAFETY_BOUNDARY.md).

## Options

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `log_level` | enum | `info` | `trace…fatal`. |
| `cloud_export_enabled` | bool | `false` | Documents explicit operator approval for non-local/cloud analytics targets. Off by default. |
| `source.mqtt_host` | str | `core-mosquitto` | Mosquitto add-on service name. |
| `source.mqtt_port` | port | `1883` | |
| `source.mqtt_username` / `source.mqtt_password` | str / password | `""` | Optional broker auth. |
| `source.topic_filter` | str | `fa/#` | MQTT topic filter to archive. |
| `tsdb.type` | enum | `influxdb` | `influxdb` (implemented) or `timescaledb` (Telegraf path below). |
| `tsdb.url` | url | `http://a0d7b954-influxdb:8086` | InfluxDB 2.x base URL (the default is the community InfluxDB add-on hostname). |
| `tsdb.influx_org` | str | `factory-assistant` | InfluxDB org. |
| `tsdb.influx_bucket` | str | `telemetry` | InfluxDB bucket. |
| `tsdb.influx_token` | password | `""` | InfluxDB API token (write scope). |
| `tsdb.measurement` | str | `fa_telemetry` | Line-protocol measurement name. |

## Data model

Topic `fa/<site>/<area>/<device>/<measurement>` is written as:

```
fa_telemetry,site=<site>,area=<area>,device=<device>,metric=<measurement>,topic=<full> value=<float>
```

`…/status` availability topics and `homeassistant/#` discovery topics are
skipped. Non-numeric payloads are skipped by the bundled exporter (use the
Telegraf path for string states / richer typing).

## Recommended production path: Telegraf

For robust ingestion (batching, retries, string fields, InfluxDB **or**
TimescaleDB), run [Telegraf](https://github.com/influxdata/telegraf) with an
`mqtt_consumer` input. Example `telegraf.conf`:

```toml
[[inputs.mqtt_consumer]]
  servers = ["tcp://core-mosquitto:1883"]
  topics  = ["fa/#"]
  data_format = "value"
  data_type   = "float"
  # username / password as needed

# InfluxDB 2.x output:
[[outputs.influxdb_v2]]
  urls         = ["http://a0d7b954-influxdb:8086"]
  token        = "$INFLUX_TOKEN"
  organization = "factory-assistant"
  bucket       = "telemetry"

# OR TimescaleDB (PostgreSQL) output:
[[outputs.postgresql]]
  connection = "host=timescaledb user=fa password=$PG_PW dbname=telemetry sslmode=disable"
```

Telegraf is read-from-MQTT / write-to-database only — same safety posture as the
bundled exporter. Telegraf is MIT-licensed.

## Status / honesty

- **Implemented:** MQTT subscribe → InfluxDB 2.x line-protocol write, numeric
  values, topic-derived tags. This is a thin exporter, not a clustered pipeline.
- **Default posture:** cloud/export analytics are disabled by default through
  `cloud_export_enabled: false`; use local on-box storage unless the operator
  deliberately approves an external telemetry store.
- **Documented (not bundled):** the Telegraf deployment above, and TimescaleDB
  output. `tsdb.type: timescaledb` is accepted by the schema but the bundled
  exporter implements InfluxDB only; it logs an error and exits if selected, so
  the documented Telegraf path is used instead.

## Safety: prohibited changes

This add-on must never gain a path that writes to a machine (PLC/OPC UA/
fieldbus) or an MQTT command/control topic. Database writes only.
