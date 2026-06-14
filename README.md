# Factory Assistant Add-ons

Industrial monitoring add-ons for
[Factory Assistant OS](https://github.com/esaueng/FactoryAssistantOS) — an
appliance-style industrial monitoring system. These add-ons install through the
Home Assistant Supervisor add-on platform that Factory Assistant runs on.

Factory Assistant is based on Home Assistant.

> ⚠️ **Safety boundary — read first.**
> Every add-on in this repository is a **read-only monitoring** tool by
> default. Factory Assistant is a monitoring, visualization, and alerting
> system — it is **not** a safety device. No add-on here implements, emulates,
> or participates in machine control, write paths, emergency stop, interlocks,
> safety PLC logic, or any safety-rated function. This is a structural boundary,
> not a tunable option. See the project safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/FactoryAssistantOS/blob/main/docs/SAFETY_BOUNDARY.md).

## Installing this repository

In the Factory Assistant / Home Assistant UI:

1. **Settings → Add-ons → Add-on Store**.
2. Top-right menu (⋮) → **Repositories**.
3. Add the Git URL: `https://github.com/esaueng/factory-assistant-addons`.
4. The roadmap add-ons below appear in the store, each installable
   individually.

This repository uses the standard Home Assistant add-on repository contract
(`repository.yaml` + one directory per add-on with a `config.yaml`), so it is
compatible with the upstream Supervisor and community add-ons.

## Add-ons

| Add-on | Purpose | Direction | Status |
| --- | --- | --- | --- |
| [`opcua-mqtt-bridge`](./opcua-mqtt-bridge) | Subscribe to OPC UA server nodes and republish to MQTT using the `fa/<site>/<area>/<device>/<measurement>` convention with MQTT discovery. | **OPC UA to MQTT, read/subscribe only. No OPC UA writes.** | Working implementation (asyncua + paho-mqtt). |
| [`plc-gateway-helper`](./plc-gateway-helper) | Poll approved Modbus TCP input/holding registers and republish telemetry to MQTT with discovery. | **Modbus read functions 3/4 only. No coils, no register writes, no safety controller use.** | Working minimal poller (pymodbus + paho-mqtt). |
| [`historian-storage`](./historian-storage) | Long-term telemetry export from Home Assistant / MQTT into a time-series database (InfluxDB / TimescaleDB path). | Reads HA/MQTT, writes to a database (a database write is **not** a machine-control path). Cloud export is off by default. | Thin MQTT to InfluxDB exporter + documented Telegraf path. |

## Optional tooling

| Add-on | Purpose | Direction | Status |
| --- | --- | --- | --- |
| [`node-red`](./node-red) | Optional protocol-glue / flow tool, wrapping the community Node-RED add-on with a read-only default posture. | Read-only by default; must not be wired for machine control on this appliance. | Wrapper / configuration + documentation. |

See each add-on's `README.md` (overview) and `DOCS.md` (configuration
reference). The read-only/monitoring boundary is restated at the top of every
add-on and in the header of every executable entrypoint.

## Validation

Run the catalog contract check before publishing changes:

```sh
bash tests/test_catalog_alignment.sh
```

## Topic and naming conventions

Add-ons that publish to MQTT use the Factory Assistant topic convention:

```
fa/<site>/<area>/<device>/<measurement>      telemetry
fa/<site>/<area>/<device>/status             per-device availability (LWT)
```

and emit Home Assistant MQTT discovery so entities are created automatically.
This matches the on-box ingestion templates shipped with Factory Assistant.

## License

Apache-2.0. See [`LICENSE`](./LICENSE) and [`NOTICE`](./NOTICE). All
first-party files in this repository are Apache-2.0; bundled third-party
components retain their own licenses (listed in `NOTICE` and each add-on's
`DOCS.md`).
