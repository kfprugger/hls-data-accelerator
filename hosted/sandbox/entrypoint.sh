#!/usr/bin/env bash
set -euo pipefail
umask 077
if [[ "${HLS_HOSTED:-0}" == 1 ]]; then
  : "${HLS_GATEWAY_KEY:?Hosted sandbox requires its gateway key}"
  : "${HLS_SANDBOX_USER_OID:?Hosted sandbox requires its portal object ID}"
  : "${HLS_SANDBOX_USER_TID:?Hosted sandbox requires its portal tenant ID}"
fi
mkdir -p "${HLS_DATA_DIR:-/data}" "${AZURE_CONFIG_DIR}" "${HOME}/.Azure"
export HLS_STATE_DIR="${HLS_DATA_DIR:-/data}/state-tracking"
mkdir -p "$HLS_STATE_DIR"
# Same backend launch used by Start-WebUI.ps1; exec preserves SIGTERM delivery.
# HOME (Azure credentials) is container-local. Only HLS_DATA_DIR is mounted.
exec /app/hls-data-accelerator/orchestrator/.venv/bin/python /app/hls-data-accelerator/orchestrator/local_server.py
