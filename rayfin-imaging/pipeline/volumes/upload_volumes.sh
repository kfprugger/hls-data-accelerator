#!/usr/bin/env bash
# Upload the 3D/4D volume catalog and its original source data to the Lakehouse (OneLake).
#
#   Files/volumes/manifest.json, Files/volumes/<study>/...      browser-ready NIfTI volumes + thumbnails
#   Files/raw/volumes/<study>/...                               original downloads, for lineage
#
# Uses your Azure CLI login (`az login`).
set -euo pipefail

# shellcheck source=/dev/null
source "$(dirname "$0")/../fabric_env.sh"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEST="https://onelake.blob.fabric.microsoft.com/${WORKSPACE_ID}/${LAKEHOUSE_ID}/Files"

export AZCOPY_AUTO_LOGIN_TYPE=AZCLI
OPTS=(--recursive --overwrite=ifSourceNewer --trusted-microsoft-suffixes=onelake.blob.fabric.microsoft.com
      --log-level=ERROR --output-level=essential)

azcopy copy "${ROOT}/work/volumes/*" "${DEST}/volumes/" "${OPTS[@]}" --exclude-pattern="study.json;manifest.json"
azcopy copy "${ROOT}/work/volumes/manifest.json" "${DEST}/volumes/manifest.json" \
  --overwrite=true --content-type=application/json --trusted-microsoft-suffixes=onelake.blob.fabric.microsoft.com

if [[ "${1:-}" == "--raw" ]]; then
  azcopy copy "${ROOT}/work/petct/study/*" "${DEST}/raw/volumes/petct-whole-body/dicom/" "${OPTS[@]}"
  azcopy copy "${ROOT}/work/totalseg/subject/*" "${DEST}/raw/volumes/totalseg-ct-angio/" "${OPTS[@]}"
  azcopy copy "${ROOT}/work/fetal_dhcp/*" "${DEST}/raw/volumes/fetal-brain-atlas/" "${OPTS[@]}"
  azcopy copy "${ROOT}/work/fetal_body/*" "${DEST}/raw/volumes/fetal-body-atlas/" "${OPTS[@]}"
  azcopy copy "${ROOT}/work/fetal_face/*" "${DEST}/raw/volumes/fetal-face-atlas/" "${OPTS[@]}"
  azcopy copy "${ROOT}/work/vhp/png/*" "${DEST}/raw/volumes/visible-human-female/png/" "${OPTS[@]}"
  azcopy copy "${ROOT}/work/lung4d/dicom/*" "${DEST}/raw/volumes/lung-4dct/dicom/" "${OPTS[@]}"
  azcopy copy "${ROOT}/work/tracts/*" "${DEST}/raw/volumes/brain-tractography/" "${OPTS[@]}" --include-pattern="*.zip;*.xlsx;*.nii.gz"
fi
echo "Uploaded to ${DEST}/volumes"
