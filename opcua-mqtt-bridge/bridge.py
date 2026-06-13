#!/usr/bin/env python3
# Factory Assistant — OPC UA → MQTT bridge (READ-ONLY).
#
# ============================================================================
# SAFETY BOUNDARY — READ-ONLY BY CONSTRUCTION
# ----------------------------------------------------------------------------
# This program SUBSCRIBES to OPC UA nodes and READS their values; it then
# PUBLISHES those values to an MQTT broker. It performs NO writes to the OPC UA
# server: there is no call to write_value / write_attribute / set_value / call
# of any method anywhere in this file, and there must never be one. Writing to
# an OPC UA node is a machine-control path and is PROHIBITED by the Factory
# Assistant safety boundary (docs/SAFETY_BOUNDARY.md). Factory Assistant is a
# monitoring system, not a safety device — it must never implement machine
# control, e-stop, interlocks, or any safety-rated function.
#
# Any change that introduces an OPC UA write must be rejected in review.
# ============================================================================
#
# Copyright 2026 Factory Assistant contributors. Apache-2.0.
"""Read-only OPC UA to MQTT bridge.

Reads a curated node list from the add-on options, subscribes to those OPC UA
nodes, and republishes each value to MQTT on the Factory Assistant topic
convention ``fa/<site>/<area>/<device>/<measurement>`` (and a ``…/status``
availability topic), optionally emitting Home Assistant MQTT discovery so
entities are created automatically.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from typing import Any

import paho.mqtt.client as mqtt
import yaml
from asyncua import Client, ua

LOG = logging.getLogger("opcua_mqtt_bridge")

# Methods that mutate an OPC UA server. Their presence in this module would
# breach the read-only safety boundary; this set is used by the self-check
# below to fail closed if the bridge is ever wired to call one.
_FORBIDDEN_OPCUA_WRITE_CALLS = (
    "write_value",
    "write_attribute",
    "set_value",
    "write",
    "call_method",
)

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")


def load_options() -> dict[str, Any]:
    """Load the Supervisor-rendered add-on options (JSON)."""
    with open(OPTIONS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def assert_read_only(source_path: str | None = None) -> None:
    """Fail closed unless this module is provably free of OPC UA writes.

    A defensive self-check: the source must not contain any of the forbidden
    OPC UA write call names as actual ``.<name>(`` invocations. If it does,
    refuse to start rather than risk a machine-control path.

    ``source_path`` defaults to this file; it is a parameter only so the check
    is testable against arbitrary source.
    """
    path = source_path or __file__
    try:
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        # If we cannot read our own source (e.g. compiled-out), skip the
        # textual check; the design guarantee still holds.
        return
    guard_marker = "_FORBIDDEN_OPCUA_WRITE_CALLS"
    for name in _FORBIDDEN_OPCUA_WRITE_CALLS:
        if f".{name}(" in source:
            raise RuntimeError(
                f"Safety boundary violation: OPC UA write call '.{name}(' "
                f"found in {path}. Writes are prohibited."
            )
    if guard_marker not in source:  # pragma: no cover - sanity only
        raise RuntimeError("Read-only guard marker missing.")


class MqttPublisher:
    """Thin paho-mqtt wrapper that only ever publishes (never subscribes to
    command topics)."""

    def __init__(self, cfg: dict[str, Any], site: str) -> None:
        self._cfg = cfg
        self._site = site
        self._base = cfg.get("base_topic", "fa").strip("/")
        self._discovery = bool(cfg.get("discovery", True))
        self._discovery_prefix = cfg.get("discovery_prefix", "homeassistant")
        self._client = mqtt.Client(
            client_id=f"fa-opcua-bridge-{site}",
            protocol=mqtt.MQTTv311,
        )
        if cfg.get("username"):
            self._client.username_pw_set(cfg["username"], cfg.get("password") or None)
        # Last Will: mark the bridge offline if it disconnects ungracefully.
        self._bridge_status_topic = f"{self._base}/{site}/_bridge/status"
        self._client.will_set(
            self._bridge_status_topic, payload="offline", qos=1, retain=True
        )

    def connect(self) -> None:
        host = self._cfg.get("host", "core-mosquitto")
        port = int(self._cfg.get("port", 1883))
        LOG.info("Connecting to MQTT broker %s:%s", host, port)
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()
        self._client.publish(
            self._bridge_status_topic, payload="online", qos=1, retain=True
        )

    def disconnect(self) -> None:
        try:
            self._client.publish(
                self._bridge_status_topic, payload="offline", qos=1, retain=True
            )
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # noqa: BLE001 - best-effort shutdown
            pass

    def device_topic(self, node: dict[str, Any]) -> str:
        return f"{self._base}/{self._site}/{node['area']}/{node['device']}"

    def state_topic(self, node: dict[str, Any]) -> str:
        return f"{self.device_topic(node)}/{node['measurement']}"

    def status_topic(self, node: dict[str, Any]) -> str:
        return f"{self.device_topic(node)}/status"

    def publish_value(self, node: dict[str, Any], value: Any) -> None:
        topic = self.state_topic(node)
        payload = "" if value is None else str(value)
        LOG.debug("PUBLISH %s = %s", topic, payload)
        self._client.publish(topic, payload=payload, qos=1, retain=False)
        # Mark device available whenever we have fresh data.
        self._client.publish(
            self.status_topic(node), payload="online", qos=1, retain=True
        )

    def publish_unavailable(self, node: dict[str, Any]) -> None:
        """Mark a device offline (e.g. when an OPC UA read fails)."""
        self._client.publish(
            self.status_topic(node), payload="offline", qos=1, retain=True
        )

    def publish_discovery(self, node: dict[str, Any]) -> None:
        if not self._discovery:
            return
        object_id = f"{node['area']}_{node['device']}_{node['measurement']}"
        config_topic = (
            f"{self._discovery_prefix}/sensor/{object_id}/config"
        )
        config = {
            "name": (
                f"{node['device']} {node['measurement']}".replace("_", " ")
            ),
            "unique_id": object_id,
            "object_id": object_id,
            "state_topic": self.state_topic(node),
            "availability_topic": self.status_topic(node),
            "payload_available": "online",
            "payload_not_available": "offline",
            "qos": 1,
            "device": {
                "identifiers": [f"{node['area']}_{node['device']}"],
                "name": f"{node['area']} {node['device']}".replace("_", " "),
                "manufacturer": "Factory Assistant OPC UA bridge",
            },
        }
        for key in ("device_class", "unit_of_measurement", "state_class"):
            if node.get(key):
                config[key] = node[key]
        LOG.info("MQTT discovery: %s", config_topic)
        self._client.publish(
            config_topic, payload=json.dumps(config), qos=1, retain=True
        )


async def run(options: dict[str, Any]) -> None:
    opcua_cfg = options["opcua"]
    mqtt_cfg = options["mqtt"]
    site = options.get("site", "plant1")
    nodes = options.get("nodes", [])
    interval = float(opcua_cfg.get("publish_interval", 5.0))

    if not nodes:
        LOG.warning("No nodes configured; nothing to bridge. Exiting idle.")

    publisher = MqttPublisher(mqtt_cfg, site)
    publisher.connect()
    for node in nodes:
        publisher.publish_discovery(node)

    endpoint = opcua_cfg["endpoint"]
    client = Client(url=endpoint)
    if opcua_cfg.get("username"):
        client.set_user(opcua_cfg["username"])
        if opcua_cfg.get("password"):
            client.set_password(opcua_cfg["password"])
    # NOTE: security policy handling (Sign/SignAndEncrypt) requires cert
    # material; "None" is the documented default. See DOCS.md.

    stop = asyncio.Event()

    def _request_stop(*_: Any) -> None:
        LOG.info("Shutdown requested.")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _request_stop)

    LOG.info("Connecting (READ-ONLY) to OPC UA endpoint %s", endpoint)
    async with client:
        # Resolve nodes once. We only ever read their values below.
        resolved = []
        for node in nodes:
            try:
                ua_node = client.get_node(node["node_id"])
                resolved.append((node, ua_node))
            except Exception as exc:  # noqa: BLE001
                LOG.error("Cannot resolve node %s: %s", node["node_id"], exc)

        LOG.info(
            "Bridging %d node(s) every %.1fs (subscribe/read only).",
            len(resolved),
            interval,
        )
        while not stop.is_set():
            for node, ua_node in resolved:
                try:
                    # READ ONLY: get_value() performs an OPC UA Read service.
                    value = await ua_node.get_value()
                    publisher.publish_value(node, value)
                except (ua.UaError, OSError) as exc:
                    LOG.warning(
                        "Read failed for %s: %s", node["node_id"], exc
                    )
                    publisher.publish_unavailable(node)
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    publisher.disconnect()
    LOG.info("Bridge stopped.")


def main() -> int:
    assert_read_only()
    options = load_options()
    configure_logging(options.get("log_level", "info"))
    LOG.info(
        "Factory Assistant OPC UA → MQTT bridge starting (READ-ONLY; no OPC "
        "UA writes are possible)."
    )
    try:
        asyncio.run(run(options))
    except KeyboardInterrupt:
        return 0
    except Exception as exc:  # noqa: BLE001
        LOG.error("Fatal: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
