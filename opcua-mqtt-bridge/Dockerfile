# Factory Assistant — OPC UA → MQTT bridge (READ-ONLY).
#
# FROM the official Home Assistant add-on base image. The Supervisor passes the
# correct per-architecture base via the BUILD_FROM build-arg (standard add-on
# contract); the ARG default lets `docker build` work standalone for amd64.
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.19
FROM ${BUILD_FROM}

# SAFETY: this image runs a subscribe/read-only OPC UA bridge. It performs no
# OPC UA writes and provides no machine-control path. See the Factory Assistant
# safety boundary (docs/SAFETY_BOUNDARY.md).

ENV LANG=C.UTF-8

# Python + build deps for asyncua/paho-mqtt wheels (musl/alpine base).
RUN apk add --no-cache python3 py3-pip

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY bridge.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Add-on metadata labels (standard HA add-on contract).
LABEL \
  io.hass.name="OPC UA → MQTT Bridge (read-only)" \
  io.hass.description="Read-only OPC UA to MQTT bridge for Factory Assistant" \
  io.hass.type="addon" \
  io.hass.version="0.1.0"

CMD ["/run.sh"]
