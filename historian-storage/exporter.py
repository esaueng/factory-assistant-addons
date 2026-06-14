#!/usr/bin/env python3
# Factory Assistant — Historian telemetry exporter.
#
# ============================================================================
# SAFETY BOUNDARY
# ----------------------------------------------------------------------------
# This program READS telemetry from MQTT (the fa/# topic tree) and WRITES it to
# a time-series database for long-term storage. Writing to a database is data
# archival, NOT a machine-control path. This program NEVER writes to a PLC,
# OPC UA server, fieldbus, or any machine I/O, and must never do so. Factory
# Assistant is a monitoring system, not a safety device (docs/SAFETY_BOUNDARY.md).
# ============================================================================
#
# Copyright 2026 Factory Assistant contributors. Apache-2.0.
"""MQTT -> InfluxDB telemetry exporter (read-from-MQTT, write-to-database).

This is a thin, dependency-light exporter that subscribes to the Factory
Assistant telemetry topic tree and writes numeric values to InfluxDB using the
line-protocol HTTP write API. For TimescaleDB or richer pipelines, see DOCS.md
(Telegraf-based deployment).
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any

import paho.mqtt.client as mqtt

LOG = logging.getLogger("historian")

OPTIONS_PATH = os.environ.get("OPTIONS_PATH", "/data/options.json")


def load_options() -> dict[str, Any]:
    with open(OPTIONS_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _finite(value: float) -> float | None:
    """Return value if it is a finite float; InfluxDB line protocol rejects
    NaN/Inf, so non-finite values are dropped (the message is skipped)."""
    return value if math.isfinite(value) else None


def parse_value(payload: bytes) -> float | None:
    """Return a finite float for a numeric payload (raw number or flat JSON),
    else None. Non-numeric payloads (e.g. text states) are skipped by this thin
    exporter; use the Telegraf path in DOCS.md for richer typing.

    Note: JSON booleans are intentionally coerced to 1.0/0.0 so binary device
    states archive as a numeric series (Python's isinstance(bool, int) is True).
    """
    text = payload.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    try:
        return _finite(float(text))
    except ValueError:
        pass
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, bool):
        return float(obj)
    if isinstance(obj, (int, float)):
        return _finite(float(obj))
    if isinstance(obj, dict):
        for key in ("value", "rate", "pressure", "temperature"):
            candidate = obj.get(key)
            if isinstance(candidate, bool):
                return float(candidate)
            if isinstance(candidate, (int, float)):
                return _finite(float(candidate))
    return None


def line_protocol(measurement: str, topic: str, value: float) -> str:
    """Build an InfluxDB line-protocol record, tagging by topic segments.

    Topic ``fa/<site>/<area>/<device>/<measurement>`` becomes tags
    site/area/device/metric so series stay queryable.
    """
    parts = topic.split("/")
    tags = {"topic": topic.replace(" ", "_")}
    if len(parts) >= 5 and parts[0] == "fa":
        tags.update(
            {
                "site": parts[1],
                "area": parts[2],
                "device": parts[3],
                "metric": parts[4],
            }
        )
    tag_str = ",".join(f"{k}={_escape_tag(v)}" for k, v in tags.items())
    return f"{measurement},{tag_str} value={value}"


def _escape_tag(value: str) -> str:
    return value.replace(",", "\\,").replace(" ", "\\ ").replace("=", "\\=")


class InfluxWriter:
    """Writes line protocol to InfluxDB 2.x over HTTP (database write only)."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self._url = cfg["url"].rstrip("/")
        self._org = cfg.get("influx_org", "")
        self._bucket = cfg.get("influx_bucket", "")
        self._token = cfg.get("influx_token", "")

    def write(self, line: str) -> None:
        endpoint = (
            f"{self._url}/api/v2/write?org={self._org}&bucket={self._bucket}"
            "&precision=s"
        )
        req = urllib.request.Request(
            endpoint, data=line.encode("utf-8"), method="POST"
        )
        req.add_header("Content-Type", "text/plain; charset=utf-8")
        if self._token:
            req.add_header("Authorization", f"Token {self._token}")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status >= 300:
                    LOG.warning("Influx write HTTP %s", resp.status)
        except urllib.error.HTTPError as exc:
            LOG.warning("Influx write failed: HTTP %s %s", exc.code, exc.reason)
        except (urllib.error.URLError, OSError) as exc:
            LOG.warning("Influx write failed: %s", exc)


def main() -> int:
    options = load_options()
    configure_logging(options.get("log_level", "info"))
    cloud_export_enabled = bool(options.get("cloud_export_enabled", False))
    source = options["source"]
    tsdb = options["tsdb"]

    if tsdb.get("type") != "influxdb":
        LOG.error(
            "tsdb.type=%s: this thin exporter implements InfluxDB only. For "
            "TimescaleDB use the Telegraf path documented in DOCS.md.",
            tsdb.get("type"),
        )
        return 1

    LOG.info(
        "Factory Assistant Historian starting: read MQTT %s, write to "
        "InfluxDB (database archival only; no machine writes). Cloud export "
        "enabled: %s.",
        source.get("topic_filter", "fa/#"),
        cloud_export_enabled,
    )

    writer = InfluxWriter(tsdb)
    measurement = tsdb.get("measurement", "fa_telemetry")

    client = mqtt.Client(client_id="fa-historian", protocol=mqtt.MQTTv311)
    if source.get("mqtt_username"):
        client.username_pw_set(
            source["mqtt_username"], source.get("mqtt_password") or None
        )

    topic_filter = source.get("topic_filter", "fa/#")

    def on_connect(cli, _userdata, _flags, rc, *_args):  # noqa: ANN001
        if rc == 0:
            LOG.info("Connected to MQTT; subscribing to %s", topic_filter)
            cli.subscribe(topic_filter, qos=1)
        else:
            LOG.error("MQTT connect failed rc=%s", rc)

    def on_message(_cli, _userdata, msg):  # noqa: ANN001
        # Skip availability/status and discovery topics; archive values only.
        if msg.topic.endswith("/status") or msg.topic.startswith(
            "homeassistant/"
        ):
            return
        value = parse_value(msg.payload)
        if value is None:
            return
        writer.write(line_protocol(measurement, msg.topic, value))

    client.on_connect = on_connect
    client.on_message = on_message

    host = source.get("mqtt_host", "core-mosquitto")
    port = int(source.get("mqtt_port", 1883))
    while True:
        try:
            client.connect(host, port, keepalive=60)
            break
        except (OSError, ConnectionError) as exc:
            LOG.warning("MQTT connect to %s:%s failed (%s); retry in 5s",
                        host, port, exc)
            time.sleep(5)

    client.loop_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
