#!/usr/bin/env bashio
# Factory Assistant — Historian Storage launcher.
#
# SAFETY: reads telemetry from MQTT and writes to a time-series database
# (archival only). No machine writes. See exporter.py header and the Factory
# Assistant safety boundary (docs/SAFETY_BOUNDARY.md).
set -euo pipefail

bashio::log.info "Factory Assistant Historian Storage (telemetry → TSDB) starting…"

exec python3 /usr/src/app/exporter.py
