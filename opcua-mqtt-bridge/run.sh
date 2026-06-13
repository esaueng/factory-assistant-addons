#!/usr/bin/env bashio
# Factory Assistant — OPC UA → MQTT bridge launcher (READ-ONLY).
#
# SAFETY: this add-on subscribes to and reads OPC UA nodes only; it never
# writes to the OPC UA server. See bridge.py header and the Factory Assistant
# safety boundary (docs/SAFETY_BOUNDARY.md).
set -euo pipefail

bashio::log.info "Factory Assistant OPC UA → MQTT bridge (READ-ONLY) starting…"

# Supervisor renders the user's options to /data/options.json; bridge.py reads
# them directly. Exec so signals (SIGTERM on stop) reach Python for clean
# shutdown.
exec python3 /usr/src/app/bridge.py
