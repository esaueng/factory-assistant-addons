# Factory Assistant — Historian Storage (telemetry → TSDB).
#
# FROM the official Home Assistant add-on base image (standard add-on
# contract). BUILD_FROM is supplied per-architecture by the Supervisor; the
# ARG default lets `docker build` work standalone for amd64.
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.19
FROM ${BUILD_FROM}

# SAFETY: this image reads MQTT telemetry and writes it to a database
# (archival). It performs no machine writes. See docs/SAFETY_BOUNDARY.md.

ENV LANG=C.UTF-8

RUN apk add --no-cache python3 py3-pip

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY exporter.py ./
COPY run.sh /run.sh
RUN chmod a+x /run.sh

LABEL \
  io.hass.name="Historian Storage (telemetry → TSDB)" \
  io.hass.description="Long-term telemetry exporter for Factory Assistant" \
  io.hass.type="addon" \
  io.hass.version="0.1.0"

CMD ["/run.sh"]
