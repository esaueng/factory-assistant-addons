# Factory Assistant — Node-RED (read-only flow tool).
#
# This add-on WRAPS the community Node-RED add-on. The Supervisor supplies the
# correct per-architecture base image via the BUILD_FROM build-arg (standard
# add-on contract). We base FROM the upstream community Node-RED add-on image so
# the Node-RED runtime, palette manager, and bashio launcher are inherited
# unchanged; this layer only adds Factory Assistant's read-only posture banner.
#
# The ARG default points at the community Node-RED add-on image for amd64 so a
# standalone `docker build` resolves; in the Supervisor, build.yaml (per-arch)
# overrides it.
ARG BUILD_FROM=ghcr.io/hassio-addons/node-red/amd64:latest
FROM ${BUILD_FROM}

# SAFETY: Node-RED here is for READ-ONLY telemetry flows. It must not be wired
# to control machines on this appliance. See docs/SAFETY_BOUNDARY.md.

# Read-only posture banner shown in the add-on log on start (advisory; the
# substantive boundary is the disabled-at-boot config, no host network, no
# hardware access, and the documented policy in DOCS.md).
COPY posture-banner.sh /etc/cont-init.d/99-fa-posture.sh
RUN chmod a+x /etc/cont-init.d/99-fa-posture.sh

LABEL \
  io.hass.name="Node-RED (read-only flow tool)" \
  io.hass.description="Read-only Node-RED flow tool for Factory Assistant" \
  io.hass.type="addon" \
  io.hass.version="0.1.0"
