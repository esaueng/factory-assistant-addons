#!/usr/bin/env bash
# Validate the installable add-on catalog against Factory Assistant OS roadmap.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

require_file() {
  local path="$1"
  [[ -f "${path}" ]] || fail "missing ${path}"
}

require_dir() {
  local path="$1"
  [[ -d "${path}" ]] || fail "missing ${path}/"
}

require_text() {
  local path="$1"
  local pattern="$2"
  grep -Eq "${pattern}" "${path}" || fail "${path} missing pattern: ${pattern}"
}

require_literal() {
  local path="$1"
  local text="$2"
  grep -Fq "${text}" "${path}" || fail "${path} missing text: ${text}"
}

require_absent() {
  local path="$1"
  local pattern="$2"
  if grep -Eq "${pattern}" "${path}"; then
    fail "${path} contains forbidden pattern: ${pattern}"
  fi
}

require_addon() {
  local dir="$1"
  local slug="$2"
  require_dir "${dir}"
  require_file "${dir}/config.yaml"
  require_file "${dir}/README.md"
  require_file "${dir}/DOCS.md"
  require_literal "${dir}/config.yaml" "slug: ${slug}"
  require_literal "${dir}/config.yaml" "startup: services"
  require_literal "${dir}/config.yaml" "boot: manual"
  require_literal "${dir}/config.yaml" "host_network: false"
  require_literal "${dir}/config.yaml" "hassio_api: false"
  require_literal "${dir}/config.yaml" "homeassistant_api: false"
  require_text "${dir}/config.yaml" '^[[:space:]]*-[[:space:]]*amd64$'
  require_absent "${dir}/config.yaml" 'privileged:[[:space:]]*true'
  require_text "${dir}/README.md" 'read-only|READ-ONLY|monitoring'
  require_text "${dir}/DOCS.md" 'safety|Safety|machine control'
}

require_file repository.yaml
require_literal repository.yaml "name: Factory Assistant Add-ons"
require_literal repository.yaml 'url: "https://github.com/esaueng/factory-assistant-addons"'

require_literal README.md "https://github.com/esaueng/FactoryAssistantOS/blob/main/docs/SAFETY_BOUNDARY.md"
old_boundary_link="github.com/esaueng/factory-assistant"
old_boundary_link+="/blob/main/docs/SAFETY_BOUNDARY.md"
if grep -R "${old_boundary_link}" README.md ./*/README.md ./*/DOCS.md \
    >/dev/null 2>&1; then
  fail "stale factory-assistant safety-boundary link found"
fi

require_addon "opcua-mqtt-bridge" "opcua_mqtt_bridge"
require_literal opcua-mqtt-bridge/config.yaml "write_nodes_allowed: false"
require_text opcua-mqtt-bridge/bridge.py 'write_nodes_allowed|assert_read_only'
require_absent opcua-mqtt-bridge/bridge.py '\.write_value\('
require_absent opcua-mqtt-bridge/bridge.py '\.write_attribute\('
require_absent opcua-mqtt-bridge/bridge.py '\.set_value\('
require_absent opcua-mqtt-bridge/bridge.py '\.call_method\('

require_addon "plc-gateway-helper" "plc_gateway_helper"
require_literal plc-gateway-helper/config.yaml "allowed_function_codes:"
require_literal plc-gateway-helper/config.yaml "write_functions_allowed: false"
require_literal plc-gateway-helper/config.yaml "safety_controller_allowed: false"
require_text plc-gateway-helper/gateway_helper.py 'allowed_function_codes|write_functions_allowed|safety_controller_allowed'
require_absent plc-gateway-helper/gateway_helper.py 'write_register|write_coil|execute_control'

require_addon "historian-storage" "historian_storage"
require_literal historian-storage/config.yaml "cloud_export_enabled: false"
require_text historian-storage/exporter.py 'cloud_export_enabled|database archival|no machine writes'

for addon in opcua-mqtt-bridge plc-gateway-helper historian-storage; do
  require_literal README.md "[\`${addon}\`](./${addon})"
done

printf 'Catalog alignment checks passed.\n'
