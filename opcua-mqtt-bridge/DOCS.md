# OPC UA → MQTT Bridge — configuration

Factory Assistant is based on Home Assistant.

> ⚠️ **Read-only / monitoring boundary.** This add-on reads OPC UA nodes and
> publishes to MQTT. It performs no OPC UA writes and provides no
> machine-control path. Configuring it for control is out of scope and
> structurally impossible. See the Factory Assistant safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/FactoryAssistantOS/blob/main/docs/SAFETY_BOUNDARY.md).

## How it works

The Supervisor renders your **Configuration** into `/data/options.json`. The
Python entrypoint (`bridge.py`, using `asyncua` + `paho-mqtt`) connects to the
OPC UA endpoint as a read-only client, reads each node on `publish_interval`,
and publishes to MQTT. A startup self-check (`assert_read_only`) refuses to
start if any OPC UA write call name is ever found in the source. The
`opcua.write_nodes_allowed` option is fixed to `false`; setting it to any other
value is a startup error.

## Options

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `log_level` | enum | `info` | `trace…fatal`. |
| `opcua.endpoint` | url | `opc.tcp://plc.example.local:4840` | OPC UA server endpoint. |
| `opcua.security` | enum | `None` | `None` / `Sign` / `SignAndEncrypt`. Non-`None` needs certificate material (not yet bundled — see Limitations). |
| `opcua.username` | str | `""` | Optional. |
| `opcua.password` | password | `""` | Optional. |
| `opcua.publish_interval` | float | `5.0` | Seconds between read cycles (0.5–3600). |
| `opcua.write_nodes_allowed` | bool | `false` | Must remain false. Any other value refuses startup. |
| `mqtt.host` | str | `core-mosquitto` | Mosquitto add-on service name. |
| `mqtt.port` | port | `1883` | |
| `mqtt.username` / `mqtt.password` | str / password | `""` | Optional broker auth. |
| `mqtt.base_topic` | str | `fa` | Topic root (`fa/<site>/…`). |
| `mqtt.discovery_prefix` | str | `homeassistant` | HA MQTT discovery prefix. |
| `mqtt.discovery` | bool | `true` | Publish retained discovery config per node. |
| `site` | str | `plant1` | First topic segment. |
| `nodes` | list | see below | One entry per measurement. |

### Node entries (`nodes`)

| Key | Type | Required | Notes |
| --- | --- | --- | --- |
| `node_id` | str | yes | OPC UA NodeId, e.g. `ns=2;s=Line1.Press03.MotorTemp`. |
| `area` | str | yes | Topic/entity segment, e.g. `line1`. |
| `device` | str | yes | Topic/entity segment, e.g. `press03`. |
| `measurement` | str | yes | Topic/entity segment, e.g. `motor_temp`. |
| `device_class` | str | no | HA device class for discovery (e.g. `temperature`). |
| `unit_of_measurement` | str | no | e.g. `°C`. |
| `state_class` | enum | no | `measurement` / `total` / `total_increasing`. |

## Topics produced

```
fa/<site>/<area>/<device>/<measurement>      value (QoS 1)
fa/<site>/<area>/<device>/status             availability (retained: online/offline)
fa/<site>/_bridge/status                     bridge liveness (LWT, retained)
```

Discovery (when enabled) is published retained to
`homeassistant/sensor/<area>_<device>_<measurement>/config`, producing
`sensor.<area>_<device>_<measurement>` — matching the Factory Assistant naming
convention used by the shipped dashboards.

## Example configuration

```yaml
log_level: info
opcua:
  endpoint: "opc.tcp://plc.example.local:4840"
  security: "None"
  publish_interval: 5.0
  write_nodes_allowed: false
mqtt:
  host: "core-mosquitto"
  port: 1883
  base_topic: "fa"
  discovery_prefix: "homeassistant"
  discovery: true
site: "plant1"
nodes:
  - node_id: "ns=2;s=Line1.Press03.MotorTemp"
    area: "line1"
    device: "press03"
    measurement: "motor_temp"
    device_class: "temperature"
    unit_of_measurement: "°C"
    state_class: "measurement"
```

## Limitations / honesty

- This is a **working implementation** of the read-only read→publish loop. It
  uses polled OPC UA reads on `publish_interval` rather than server-side
  monitored-item subscriptions; both are read-only, and polling is simpler and
  robust against servers with limited subscription support. A subscription
  (monitored-items) mode is a natural future addition.
- `security: Sign` / `SignAndEncrypt` is accepted by the schema but the add-on
  does not yet ship certificate provisioning; use `None` (e.g. on a trusted
  OT network segment) until certificate handling lands. This does not affect
  the read-only guarantee.
- Values are published as their string representation; complex/struct node
  values are stringified. Add a `value_template` on the HA side if needed.

## Safety: prohibited changes

Any change that adds an OPC UA write (`write_value`, `write_attribute`,
`set_value`, `call_method`, etc.), an MQTT command/control topic, host network,
hardware access, or Supervisor write roles must be rejected in review. The
read-only posture is a structural safety boundary, not a configurable option.
