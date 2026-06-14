#!/usr/bin/env python3
# Factory Assistant — PLC Gateway Helper (READ-ONLY).
#
# ============================================================================
# SAFETY BOUNDARY — READ-ONLY MODBUS TELEMETRY ONLY
# ----------------------------------------------------------------------------
# This program polls Modbus TCP input/holding registers with function codes 3
# and 4, then publishes telemetry to MQTT. It provides NO machine-control path,
# does not write coils or registers, and refuses startup if configuration tries
# to enable write functions or safety controller access. Factory Assistant is a
# monitoring system, not a safety device.
# ============================================================================
#
# Copyright 2026 Factory Assistant contributors. Apache-2.0.
"""Read-only Modbus TCP to MQTT telemetry helper."""
from __future__ import annotations

import json
import logging
import math
import os
import signal
import struct
import sys
import time
from typing import Any

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

LOG = logging.getLogger("plc_gateway_helper")

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")
READ_ONLY_FUNCTION_CODES = {3, 4}


def load_options() -> dict[str, Any]:
    with open(OPTIONS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def validate_read_only_options(options: dict[str, Any]) -> None:
    modbus = options.get("modbus", {})
    allowed_function_codes = set(modbus.get("allowed_function_codes", []))
    if not allowed_function_codes:
        raise RuntimeError("modbus.allowed_function_codes must not be empty.")
    if not allowed_function_codes.issubset(READ_ONLY_FUNCTION_CODES):
        raise RuntimeError(
            "Safety boundary violation: only Modbus function codes 3 and 4 "
            "are allowed."
        )
    if modbus.get("write_functions_allowed") is not False:
        raise RuntimeError(
            "Safety boundary violation: modbus.write_functions_allowed must "
            "be false."
        )
    if modbus.get("safety_controller_allowed") is not False:
        raise RuntimeError(
            "Safety boundary violation: modbus.safety_controller_allowed must "
            "be false."
        )
    for register in options.get("registers", []):
        function_code = int(register.get("function_code", 3))
        if function_code not in allowed_function_codes:
            raise RuntimeError(
                f"Register {register.get('measurement')} uses function code "
                f"{function_code}, which is not in allowed_function_codes."
            )


class MqttPublisher:
    """Publish telemetry and discovery; never subscribes to command topics."""

    def __init__(self, cfg: dict[str, Any], site: str) -> None:
        self._cfg = cfg
        self._site = site
        self._base = cfg.get("base_topic", "fa").strip("/")
        self._discovery = bool(cfg.get("discovery", True))
        self._discovery_prefix = cfg.get("discovery_prefix", "homeassistant")
        self._client = mqtt.Client(
            client_id=f"fa-plc-gateway-{site}",
            protocol=mqtt.MQTTv311,
        )
        if cfg.get("username"):
            self._client.username_pw_set(cfg["username"], cfg.get("password") or None)
        self._status_topic = f"{self._base}/{site}/_plc_gateway/status"
        self._client.will_set(self._status_topic, payload="offline", qos=1, retain=True)

    def connect(self) -> None:
        host = self._cfg.get("host", "core-mosquitto")
        port = int(self._cfg.get("port", 1883))
        LOG.info("Connecting to MQTT broker %s:%s", host, port)
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()
        self._client.publish(self._status_topic, payload="online", qos=1, retain=True)

    def disconnect(self) -> None:
        try:
            self._client.publish(self._status_topic, payload="offline", qos=1, retain=True)
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001 - best-effort shutdown
            pass

    def device_topic(self, register: dict[str, Any]) -> str:
        return f"{self._base}/{self._site}/{register['area']}/{register['device']}"

    def state_topic(self, register: dict[str, Any]) -> str:
        return f"{self.device_topic(register)}/{register['measurement']}"

    def status_topic(self, register: dict[str, Any]) -> str:
        return f"{self.device_topic(register)}/status"

    def publish_value(self, register: dict[str, Any], value: Any) -> None:
        topic = self.state_topic(register)
        payload = "" if value is None else str(value)
        self._client.publish(topic, payload=payload, qos=1, retain=False)
        self._client.publish(self.status_topic(register), payload="online", qos=1, retain=True)

    def publish_unavailable(self, register: dict[str, Any]) -> None:
        self._client.publish(self.status_topic(register), payload="offline", qos=1, retain=True)

    def publish_discovery(self, register: dict[str, Any]) -> None:
        if not self._discovery:
            return
        object_id = f"{register['area']}_{register['device']}_{register['measurement']}"
        config_topic = f"{self._discovery_prefix}/sensor/{object_id}/config"
        config = {
            "name": f"{register['device']} {register['measurement']}".replace("_", " "),
            "unique_id": object_id,
            "object_id": object_id,
            "state_topic": self.state_topic(register),
            "availability_topic": self.status_topic(register),
            "payload_available": "online",
            "payload_not_available": "offline",
            "qos": 1,
            "device": {
                "identifiers": [f"{register['area']}_{register['device']}"],
                "name": f"{register['area']} {register['device']}".replace("_", " "),
                "manufacturer": "Factory Assistant PLC gateway helper",
            },
        }
        for key in ("device_class", "unit_of_measurement", "state_class"):
            if register.get(key):
                config[key] = register[key]
        self._client.publish(config_topic, payload=json.dumps(config), qos=1, retain=True)


def read_register(client: ModbusTcpClient, unit_id: int, register: dict[str, Any]) -> Any:
    function_code = int(register.get("function_code", 3))
    address = int(register["address"])
    count = int(register.get("count", 1))
    if function_code == 3:
        result = _read_with_unit(client.read_holding_registers, address, count, unit_id)
    elif function_code == 4:
        result = _read_with_unit(client.read_input_registers, address, count, unit_id)
    else:  # pragma: no cover - validate_read_only_options blocks this.
        raise RuntimeError(f"Unsupported read-only function code {function_code}.")
    if result.isError():
        raise RuntimeError(str(result))
    return decode_registers(result.registers, register)


def _read_with_unit(method: Any, address: int, count: int, unit_id: int) -> Any:
    """Call pymodbus read methods across minor API naming differences."""
    try:
        return method(address=address, count=count, slave=unit_id)
    except TypeError:
        return method(address=address, count=count, unit=unit_id)


def decode_registers(registers: list[int], register_cfg: dict[str, Any]) -> Any:
    data_type = register_cfg.get("data_type", "uint16")
    scale = float(register_cfg.get("scale", 1.0))
    offset = float(register_cfg.get("offset", 0.0))
    if data_type == "uint16":
        value = registers[0]
    elif data_type == "int16":
        value = registers[0] - 65536 if registers[0] & 0x8000 else registers[0]
    elif data_type in {"uint32", "int32", "float32"}:
        if len(registers) < 2:
            raise RuntimeError(f"{data_type} requires count: 2.")
        raw = ((registers[0] & 0xFFFF) << 16) | (registers[1] & 0xFFFF)
        if data_type == "uint32":
            value = raw
        elif data_type == "int32":
            value = raw - 0x100000000 if raw & 0x80000000 else raw
        else:
            value = struct.unpack(">f", raw.to_bytes(4, "big"))[0]
    elif data_type == "bool":
        value = bool(registers[0])
    else:
        raise RuntimeError(f"Unsupported data_type: {data_type}")
    if isinstance(value, bool):
        return value
    numeric = value * scale + offset
    if isinstance(numeric, float) and not math.isfinite(numeric):
        raise RuntimeError("Decoded value is not finite.")
    return numeric


def run(options: dict[str, Any]) -> None:
    validate_read_only_options(options)
    modbus = options["modbus"]
    registers = options.get("registers", [])
    interval = float(modbus.get("poll_interval", 5.0))
    site = options.get("site", "plant1")
    stop = False

    def _request_stop(*_: Any) -> None:
        nonlocal stop
        LOG.info("Shutdown requested.")
        stop = True

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    publisher = MqttPublisher(options["mqtt"], site)
    publisher.connect()
    for register in registers:
        publisher.publish_discovery(register)

    client = ModbusTcpClient(
        host=modbus["host"],
        port=int(modbus.get("port", 502)),
        timeout=float(modbus.get("timeout", 3.0)),
    )
    unit_id = int(modbus.get("unit_id", 1))

    LOG.info(
        "Starting read-only Modbus polling for %d register(s) every %.1fs.",
        len(registers),
        interval,
    )
    while not stop:
        if not client.connected and not client.connect():
            LOG.warning("Modbus connect to %s:%s failed.", modbus["host"], modbus.get("port", 502))
            time.sleep(min(interval, 5.0))
            continue
        for register in registers:
            try:
                value = read_register(client, unit_id, register)
                publisher.publish_value(register, value)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("Read failed for %s: %s", register.get("measurement"), exc)
                publisher.publish_unavailable(register)
        time.sleep(interval)

    client.close()
    publisher.disconnect()


def main() -> int:
    options = load_options()
    configure_logging(options.get("log_level", "info"))
    try:
        run(options)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        LOG.error("Fatal: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
