#!/usr/bin/env bash
# Validate GHCR image wiring for installable Factory Assistant add-ons.
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

require_literal() {
  local path="$1"
  local text="$2"
  grep -Fq "${text}" "${path}" || fail "${path} missing text: ${text}"
}

require_absent() {
  local path="$1"
  local text="$2"
  if grep -Fq "${text}" "${path}"; then
    fail "${path} contains unsupported image arch: ${text}"
  fi
}

require_image_field() {
  local dir="$1"
  local package="$2"

  require_file "${dir}/config.yaml"
  require_file "${dir}/Dockerfile"
  require_literal "${dir}/config.yaml" \
    "image: ghcr.io/esaueng/{arch}-addon-${package}"
  require_literal "${dir}/config.yaml" "  - amd64"
  require_absent "${dir}/config.yaml" "  - aarch64"
  require_absent "${dir}/config.yaml" "  - armv7"
}

workflow=".github/workflows/build-addon-images.yml"

require_image_field "opcua-mqtt-bridge" "opcua-mqtt-bridge"
require_image_field "plc-gateway-helper" "plc-gateway-helper"
require_image_field "historian-storage" "historian-storage"

require_file "${workflow}"
require_literal "${workflow}" "name: Build add-on images"
require_literal "${workflow}" "packages: write"
require_literal "${workflow}" "docker/setup-buildx-action@v3"
require_literal "${workflow}" "docker/login-action@v3"
require_literal "${workflow}" "docker/build-push-action@v6"
require_literal "${workflow}" "opcua-mqtt-bridge"
require_literal "${workflow}" "plc-gateway-helper"
require_literal "${workflow}" "historian-storage"
require_literal "${workflow}" "ghcr.io/esaueng/amd64-addon-opcua-mqtt-bridge"
require_literal "${workflow}" "ghcr.io/esaueng/amd64-addon-plc-gateway-helper"
require_literal "${workflow}" "ghcr.io/esaueng/amd64-addon-historian-storage"
require_literal "${workflow}" 'version: "0.1.0"'
require_literal "${workflow}" '${{ matrix.image }}:${{ matrix.version }}'
require_literal "${workflow}" 'push: ${{ github.event_name != '"'"'pull_request'"'"' && (github.ref == '"'"'refs/heads/main'"'"' || startsWith(github.ref, '"'"'refs/tags/'"'"') || inputs.publish_images == true) }}'

require_literal ".github/workflows/lint.yml" "bash tests/test_image_publish_workflow.sh"
require_literal "README.md" "bash tests/test_image_publish_workflow.sh"

printf 'Image publish workflow checks passed.\n'
