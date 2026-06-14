#!/usr/bin/env bashio
# Factory Assistant — PLC Gateway Helper launcher (READ-ONLY).
#
# SAFETY: this add-on polls Modbus input/holding registers only and publishes
# telemetry to MQTT. It never writes coils/registers and must not be connected
# to safety controllers. See gateway_helper.py and the Factory Assistant safety
# boundary (docs/SAFETY_BOUNDARY.md).
set -euo pipefail

bashio::log.info "Factory Assistant PLC Gateway Helper (READ-ONLY) starting..."

exec python3 /usr/src/app/gateway_helper.py
