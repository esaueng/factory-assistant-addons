# Node-RED (read-only flow tool) — configuration

Factory Assistant is based on Home Assistant.

> ⚠️ **Read-only posture on this appliance.** Node-RED may read and transform
> telemetry only. It must not be wired to control machines or implement any
> safety function. See the Factory Assistant safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/factory-assistant/blob/main/docs/SAFETY_BOUNDARY.md).

## What this add-on is

A thin wrapper over the community
[Node-RED add-on](https://github.com/hassio-addons/addon-node-red). `build.yaml`
bases each architecture FROM the upstream community image; the only Factory
Assistant additions are the read-only posture defaults in `config.yaml`, a
start-up banner, and this documentation. The Node-RED runtime, palette manager,
and bashio launcher are inherited unchanged, keeping the add-on contract
compatible.

## Options

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `log_level` | enum | `info` | `trace…fatal`. |
| `read_only_posture` | bool | `true` | Advisory flag; logs the boundary on start. Setting it `false` does **not** authorize machine control. |
| `credential_secret` | password | `""` | Optional secret to encrypt stored flow credentials (passed through to Node-RED). |

(The upstream community add-on exposes many more options. This wrapper keeps a
minimal surface; advanced users can extend `config.yaml` while preserving the
read-only posture and the unchanged add-on contract.)

## Permitted vs prohibited node types

**Permitted (read / transform / present):**

- `mqtt in`, `http in`, `websocket in`, `inject`, `function`, `change`,
  `switch`, `template`, dashboard/UI nodes, `debug`.
- Home Assistant *state* / *event* read nodes.
- Outputs that write to **databases** or dashboards (archival/visualization).

**Prohibited on this appliance:**

- Any node that writes to a machine protocol: PLC/OPC UA write nodes, Modbus
  *write* (coil/register) nodes, fieldbus output nodes.
- `mqtt out` to a **command/control** topic that actuates a machine.
- Home Assistant *service-call* nodes that command physical outputs.
- Any flow emulating e-stop, interlock, safety-PLC, or safety-rated logic.

## Why this is policy + review, not a hard sandbox

Node-RED is a general-purpose flow engine; it cannot be made physically
incapable of writing while remaining Node-RED. The boundary here is enforced by
(1) configuration that removes the easy paths to machine I/O (disabled at boot,
no host network, no hardware/device mapping), (2) a visible start-up banner, and
(3) documented policy plus the Factory Assistant review gate that rejects any
machine-write/control path. Operators are responsible for keeping flows
read-only. If you need a guaranteed read-only OPC UA→MQTT path, use the
`opcua-mqtt-bridge` add-on, which is read-only by construction.

## Safety: prohibited changes

Do not add machine-write output nodes, command/control flows, or any
safety-rated logic. Keep `boot: manual`, `host_network: false`, and no hardware
mapping.
