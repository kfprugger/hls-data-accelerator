#!/usr/bin/env bash
# Upload the generated Deep Zoom pyramids, manifest and (optionally) the raw SVS slides
# to the Lakehouse Files area in OneLake. Uses your Azure CLI login (`az login`).
#
#   pipeline/upload_to_onelake.sh            # tiles + manifest
#   pipeline/upload_to_onelake.sh --raw      # also upload the original .svs files to Files/raw
set -euo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/fabric_env.sh"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="https://onelake.blob.fabric.microsoft.com/${WORKSPACE_ID}/${LAKEHOUSE_ID}/Files"

export AZCOPY_AUTO_LOGIN_TYPE=AZCLI
COMMON=(--recursive --overwrite=ifSourceNewer --trusted-microsoft-suffixes=onelake.blob.fabric.microsoft.com
        --log-level=ERROR --output-level=essential)

azcopy copy "${ROOT}/work/lakehouse/slides" "${DEST}/" "${COMMON[@]}" --content-type=image/jpeg \
  --include-pattern="*.jpg"
azcopy copy "${ROOT}/work/lakehouse/slides" "${DEST}/" "${COMMON[@]}" --include-pattern="*.dzi;*.json"
azcopy copy "${ROOT}/work/lakehouse/manifest.json" "${DEST}/manifest.json" \
  --overwrite=true --trusted-microsoft-suffixes=onelake.blob.fabric.microsoft.com --content-type=application/json

if [[ "${1:-}" == "--raw" ]]; then
  azcopy copy "${ROOT}/work/raw" "${DEST}/" "${COMMON[@]}" --include-pattern="*.svs"
  # Multiplexed immunofluorescence: the marker images (DICOM slide microscopy) used for the channel pyramids.
  if [[ -d "${ROOT}/work/mif/level4" ]]; then
    azcopy copy "${ROOT}/work/mif/level4/*" "${DEST}/raw/colon-cycif/" "${COMMON[@]}"
  fi
fi
echo "Uploaded to ${DEST}"
