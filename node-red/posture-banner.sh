#!/usr/bin/env bashio
# Factory Assistant — Node-RED read-only posture banner.
#
# Advisory init step (runs via s6 cont-init). It logs the read-only/monitoring
# boundary on every start. The substantive boundary is config (disabled at
# boot, no host network, no hardware access) plus the documented policy in
# DOCS.md — this banner makes the posture visible in the add-on log.
set -euo pipefail

bashio::log.warning "Factory Assistant Node-RED: READ-ONLY POSTURE."
bashio::log.warning "Use Node-RED flows to READ and TRANSFORM telemetry only."
bashio::log.warning "Do NOT wire flows to control machines, write to PLC/OPC UA"
bashio::log.warning "outputs, or implement e-stop/interlock/safety logic."
bashio::log.warning "Factory Assistant is a monitoring system, not a safety"
bashio::log.warning "device. See docs/SAFETY_BOUNDARY.md."

if bashio::config.true 'read_only_posture'; then
  bashio::log.info "read_only_posture=true (recommended)."
else
  bashio::log.warning "read_only_posture=false set by operator — this does NOT"
  bashio::log.warning "permit machine control; the safety boundary still applies."
fi
