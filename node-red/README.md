# Node-RED (read-only flow tool)

An **optional** Node-RED flow / protocol-glue tool for Factory Assistant. It
wraps the community
[Node-RED add-on](https://github.com/hassio-addons/addon-node-red) and adds a
**read-only default posture** appropriate for a monitoring appliance: use it to
read, transform, route, and visualize telemetry — never to control machines.

Factory Assistant is based on Home Assistant.

> ⚠️ **Safety boundary — read-only on this appliance.**
> Node-RED is a general flow engine that *can* write to many protocols. On
> Factory Assistant it must be used with a **read-only posture**: flows may
> subscribe to MQTT, read Home Assistant state, and transform/forward data, but
> must **not** be wired to control machines, write to PLC/OPC UA outputs, or
> implement e-stop, interlock, or any safety-rated function. Factory Assistant
> is a monitoring system, not a safety device. This add-on ships **disabled at
> boot**, with **no host network** and **no hardware access**, so it cannot
> reach machine I/O out of the box. See the project safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/factory-assistant/blob/main/docs/SAFETY_BOUNDARY.md).

## What it is for

- Read-only protocol glue: bridge/transform telemetry between MQTT, HTTP,
  WebSocket, and Home Assistant for dashboards and notifications.
- Light data shaping the on-box templates do not cover.

## What it must not be used for

- Writing to PLCs, OPC UA outputs, Modbus coils/registers, or any fieldbus.
- MQTT command/control topics that act on a machine.
- Any e-stop, interlock, safety-PLC, or safety-rated logic ("soft"/"virtual"
  variants included).

## How the read-only posture is enforced

| Mechanism | Effect |
| --- | --- |
| `boot: manual` | Add-on does not auto-start; an operator enables it deliberately. |
| `host_network: false`, no `devices`/`uart`/`gpio` | No direct path to machine I/O or fieldbus hardware. |
| `read_only_posture` option (default `true`) | Logs the boundary on start; documents intent. |
| Start-up banner | Restates the read-only/monitoring boundary in the add-on log. |
| Documentation | `DOCS.md` states permitted vs prohibited node types. |

These are posture controls, not a cryptographic sandbox: Node-RED is inherently
flexible. The boundary is ultimately a **policy + review** control — see
`DOCS.md`.

## Quick start

1. Install this add-on; open it (Ingress) from the sidebar after enabling.
2. Build read-only flows (MQTT `in`, HA state, function/transform, dashboard).
3. Do **not** install or use output nodes that write to machine protocols.

Reference: [`DOCS.md`](./DOCS.md).

## Status / honesty

This is a **thin wrapper** over the community Node-RED add-on (it inherits that
image and runtime via `build.yaml`) plus Factory Assistant's read-only posture
(config defaults, start-up banner, documentation). It does not fork or modify
Node-RED itself.

## License

Apache-2.0 for the Factory Assistant wrapper (see repository `LICENSE` /
`NOTICE`). Node-RED and the community Node-RED add-on are Apache-2.0 and retain
their own attribution.
