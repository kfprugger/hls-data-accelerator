"""Validated application of operator hotfix tars inside a hosted sandbox.

A hotfix tar in the sandbox's own ``HLS_DATA_DIR`` is applied only when it carries a ``.hls-hotfix-commit``
member whose content equals the ``HLS_IMAGE_COMMIT`` baked into the running image. A tar without that
marker, or built for another image, is renamed ``<name>.rejected`` and never unpacked. After a successful
unpack the tar becomes ``<name>.applied``; the container filesystem is ephemeral, so the entrypoint re-applies
``.applied`` tars at boot while their marker still matches the image. Unpack failures raise ``HotfixError``.

Runs standalone from ``hosted/sandbox/entrypoint.sh`` (exit 1 on failure), so it imports nothing from the
orchestrator package.
"""
from __future__ import annotations

import logging
import os
import sys
import tarfile
from pathlib import Path

MARKER = ".hls-hotfix-commit"
ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("hls.hotfix")


class HotfixError(RuntimeError):
    pass


def default_targets() -> list[tuple[str, Path]]:
    return [("hotfix.tar", ROOT), ("wardflow-fix.tar", Path(os.environ.get("WARDFLOW_ROOT", "/app/wardflow")))]


def _member_name(member: tarfile.TarInfo) -> str:
    return member.name.removeprefix("./")


def _marker(members: list[tarfile.TarInfo], tf: tarfile.TarFile) -> str:
    member = next((m for m in members if _member_name(m) == MARKER), None)
    if member is None or not member.isfile() or member.size > 128:
        return ""
    handle = tf.extractfile(member)
    return handle.read().decode("ascii", errors="replace").strip() if handle else ""


def _extract(tar_path: Path, dest: Path, commit: str) -> str:
    """Unpack ``tar_path`` into ``dest``; return "" when applied, else the rejection reason."""
    with tarfile.open(tar_path, "r") as tf:
        members = tf.getmembers()
        marker = _marker(members, tf)
        if not commit:
            return "this image has no HLS_IMAGE_COMMIT, so no hotfix can be validated"
        if not marker:
            return f"it has no {MARKER} marker"
        if marker != commit:
            return f"its marker {marker[:40]!r} does not match image commit {commit!r}"
        tf.extractall(dest, members=[m for m in members if _member_name(m) != MARKER], filter="data")
    return ""


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def apply_hotfixes(data_dir: Path, targets: list[tuple[str, Path]], *, reapply_applied: bool) -> list[Path]:
    """Apply validated hotfix tars from ``data_dir``; return the destinations that changed."""
    data_dir = Path(data_dir).resolve()
    shared = os.environ.get("HLS_SHARED_DATA_DIR", "").strip()
    if shared and _is_within(data_dir, Path(shared).resolve()):
        raise HotfixError(f"Refusing to apply hotfixes from the shared share root {data_dir}")
    commit = os.environ.get("HLS_IMAGE_COMMIT", "").strip()
    changed: list[Path] = []
    for name, dest in targets:
        pending, applied = data_dir / name, data_dir / f"{name}.applied"
        sources = ([applied] if reapply_applied and applied.is_file() else []) + ([pending] if pending.is_file() else [])
        for source in sources:
            try:
                reason = _extract(source, dest, commit)
            except (tarfile.TarError, OSError, ValueError) as exc:
                raise HotfixError(f"Hotfix {source} could not be unpacked into {dest}: {exc}") from exc
            if reason:
                os.replace(source, data_dir / f"{name}.rejected")
                log.warning("Rejected %s: %s. Renamed to %s.rejected.", source, reason, name)
                continue
            if source == pending:
                os.replace(pending, applied)
            log.info("Applied %s into %s (image commit %s).", source.name, dest, commit)
            changed.append(dest)
    return changed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s hotfix: %(message)s", stream=sys.stderr)
    try:
        apply_hotfixes(Path(os.environ.get("HLS_DATA_DIR") or "/data"), default_targets(), reapply_applied=True)
    except HotfixError as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
