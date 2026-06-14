# PLC Gateway Helper — configuration

Factory Assistant is based on Home Assistant.

> ⚠️ **Read-only / monitoring boundary.** This add-on polls Modbus TCP input or
> holding registers and publishes telemetry to MQTT. It performs no Modbus
> writes, provides no machine-control path, and must not connect to safety
> controllers. See the Factory Assistant safety boundary:
> [`docs/SAFETY_BOUNDARY.md`](https://github.com/esaueng/FactoryAssistantOS/blob/main/docs/SAFETY_BOUNDARY.md).

## How it works

The Supervisor renders your **Configuration** into `/data/options.json`. The
Python entrypoint (`gateway_helper.py`, using `pymodbus` + `paho-mqtt`) connects
to one Modbus TCP endpoint, polls each configured register on `poll_interval`,
and publishes decoded values to MQTT. Startup validation refuses to run unless:

- `modbus.allowed_function_codes` is a non-empty subset of `[3, 4]`.
- `modbus.write_functions_allowed` is `false`.
- `modbus.safety_controller_allowed` is `false`.
- Every register uses one of the allowed read function codes.

## Options

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `log_level` | enum | `info` | `trace…fatal`. |
| `site` | str | `plant1` | First MQTT topic segment. |
| `mqtt.host` | str | `core-mosquitto` | Mosquitto add-on service name. |
| `mqtt.port` | port | `1883` | |
| `mqtt.username` / `mqtt.password` | str / password | `""` | Optional broker auth. |
| `mqtt.base_topic` | str | `fa` | Topic root (`fa/<site>/...`). |
| `mqtt.discovery_prefix` | str | `homeassistant` | HA MQTT discovery prefix. |
| `mqtt.discovery` | bool | `true` | Publish retained discovery config per register. |
| `modbus.host` | str | `plc.example.local` | Modbus TCP endpoint. |
| `modbus.port` | port | `502` | Modbus TCP port. |
| `modbus.unit_id` | int | `1` | Slave/unit id. |
| `modbus.poll_interval` | float | `5.0` | Seconds between read cycles (0.5-3600). |
| `modbus.timeout` | float | `3.0` | TCP read timeout. |
| `modbus.allowed_function_codes` | list | `[3, 4]` | Read Holding Registers and Read Input Registers only. |
| `modbus.write_functions_allowed` | bool | `false` | Must remain false. |
| `modbus.safety_controller_allowed` | bool | `false` | Must remain false; safety PLCs/controllers are out of scope. |
| `registers` | list | see below | One entry per measurement. |

### Register entries (`registers`)

| Key | Type | Required | Notes |
| --- | --- | --- | --- |
| `function_code` | enum | yes | `3` for holding registers or `4` for input registers. |
| `address` | int | yes | Register address expected by the target gateway. |
| `count` | int | yes | `1` for 16-bit/bool, `2` for 32-bit/float. |
| `area` | str | yes | Topic/entity segment, e.g. `line1`. |
| `device` | str | yes | Topic/entity segment, e.g. `press03`. |
| `measurement` | str | yes | Topic/entity segment, e.g. `cycle_count`. |
| `data_type` | enum | yes | `uint16`, `int16`, `uint32`, `int32`, `float32`, or `bool`. |
| `scale` | float | yes | Multiplier for numeric values. |
| `offset` | float | yes | Offset added after scaling. |
| `unit_of_measurement` | str | no | e.g. `rpm`, `bar`, `count`. |
| `device_class` | str | no | HA device class for discovery. |
| `state_class` | enum | no | `measurement`, `total`, or `total_increasing`. |

## Topics produced

```
fa/<site>/<area>/<device>/<measurement>      value (QoS 1)
fa/<site>/<area>/<device>/status             availability (retained: online/offline)
fa/<site>/_plc_gateway/status                helper liveness (LWT, retained)
```

Discovery (when enabled) is published retained to
`homeassistant/sensor/<area>_<device>_<measurement>/config`, producing
`sensor.<area>_<device>_<measurement>`.

## Example configuration

```yaml
log_level: info
site: "plant1"
mqtt:
  host: "core-mosquitto"
  port: 1883
  base_topic: "fa"
  discovery_prefix: "homeassistant"
  discovery: true
modbus:
  host: "plc.example.local"
  port: 502
  unit_id: 1
  poll_interval: 5.0
  timeout: 3.0
  allowed_function_codes:
    - 3
    - 4
  write_functions_allowed: false
  safety_controller_allowed: false
registers:
  - function_code: 3
    address: 40001
    count: 1
    area: "line1"
    device: "press03"
    measurement: "cycle_count"
    data_type: "uint16"
    scale: 1.0
    offset: 0.0
    unit_of_measurement: ""
    state_class: "measurement"
```

## Safety: prohibited changes

Any change that adds Modbus writes, coil/control paths, MQTT command topics,
host networking, hardware access, Supervisor write roles, or safety controller
integration must be rejected in review. This add-on is a monitoring helper, not
a control gateway.
