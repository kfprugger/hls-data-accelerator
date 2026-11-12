# Sourced by the upload scripts: loads WORKSPACE_ID / LAKEHOUSE_ID from the environment or from
# fabric.env at the repository root (written by scripts/setup_fabric.py). Environment variables win.
_FABRIC_ENV="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/fabric.env"
if [[ -f "${_FABRIC_ENV}" ]]; then
  while IFS='=' read -r _k _v; do
    case "${_k}" in
      WORKSPACE_ID) WORKSPACE_ID="${WORKSPACE_ID:-${_v}}" ;;
      LAKEHOUSE_ID) LAKEHOUSE_ID="${LAKEHOUSE_ID:-${_v}}" ;;
    esac
  done < "${_FABRIC_ENV}"
fi
if [[ -z "${WORKSPACE_ID:-}" || -z "${LAKEHOUSE_ID:-}" ]]; then
  echo "WORKSPACE_ID / LAKEHOUSE_ID not set. Run: python scripts/setup_fabric.py --workspace <name>" >&2
  exit 1
fi
