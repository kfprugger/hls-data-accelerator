"""Rotating maximum intensity projections (MIP) -> sprite sheets for the viewer's MIP mode.

For each study listed below, the volume is rotated about the head-to-foot axis in N steps and projected
front to back, keeping the brightest voxel along every ray. The frames are packed into one 8-bit PNG.

Output: work/volumes/<study>/mip.png and a `mip` block added to work/volumes/<study>/study.json
"""
import json
import math
import pathlib
import re

import nibabel as nib
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
VOL = ROOT / "work" / "volumes"
FRAMES = 40
COLS = 8

# study id, file, window (lo, hi), label, default colour map, optional (label map, LUT, name pattern) to remove
TARGETS = [
    ("petct-whole-body", "pet_suv.nii.gz", (0.0, 8.0), "PET MIP, SUV 0 to 8", "inverted", None),
    ("totalseg-ct-angio", "ct.nii.gz", (150.0, 550.0), "CT angiography MIP, bone removed, 150 to 550 HU", "gray",
     ("structures.nii.gz", "structures.lut.json",
      r"vertebra|rib|sternum|skull|humerus|scapula|clavicula|femur|hip|sacrum|costal")),
]


def rotating_mip(path: pathlib.Path, lo: float, hi: float, remove=None) -> tuple[list[np.ndarray], float]:
    img = nib.as_closest_canonical(nib.load(path))  # RAS: x L->R, y P->A, z I->S
    data = np.asanyarray(img.dataobj).astype(np.float32)
    if remove:
        labels_file, lut_file, pattern = remove
        lab = np.asanyarray(nib.as_closest_canonical(nib.load(path.parent / labels_file)).dataobj)
        lut = json.loads((path.parent / lut_file).read_text())
        ids = [i for i, n in zip(lut["I"], lut["labels"]) if n and re.search(pattern, n.lower().replace(" ", "_"))]
        bone = ndimage.binary_dilation(np.isin(lab, ids), iterations=2)
        data[bone] = lo  # digital subtraction of the skeleton
        data[data > 560] = lo  # residual cortical bone and calcium, denser than contrast-filled vessels

    zx, zy, zz = img.header.get_zooms()[:3]
    # Isotropic in-plane, keep z and fix aspect when packing.
    if abs(zx - zy) > 1e-3:
        data = ndimage.zoom(data, (1, zy / zx, 1), order=1)
    data = np.clip((data - lo) / (hi - lo), 0, 1)
    nx, ny, nz = data.shape
    side = int(math.ceil(math.hypot(nx, ny)))
    pad = np.zeros((side, side, nz), np.float32)
    ox, oy = (side - nx) // 2, (side - ny) // 2
    pad[ox:ox + nx, oy:oy + ny] = data
    frames = []
    for i in range(FRAMES):
        rot = ndimage.rotate(pad, 360.0 * i / FRAMES, axes=(0, 1), reshape=False, order=1, prefilter=False)
        proj = rot.max(axis=1)  # (x, z): looking from the front
        frames.append(proj[::-1, ::-1].T)  # superior at top, patient right on image left
    return frames, zz / zx


def crop_box(frames: list[np.ndarray]) -> tuple[slice, slice]:
    any_ = np.max(np.stack(frames), axis=0) > 0.02
    ys, xs = np.nonzero(any_)
    return slice(max(0, ys.min() - 4), ys.max() + 5), slice(max(0, xs.min() - 4), xs.max() + 5)


def main() -> None:
    for study_id, fname, (lo, hi), label, cmap, remove in TARGETS:
        if not (VOL / study_id / fname).exists():
            continue
        frames, aspect = rotating_mip(VOL / study_id / fname, lo, hi, remove)
        sy, sx = crop_box(frames)
        frames = [f[sy, sx] for f in frames]
        h, w = frames[0].shape
        h2 = int(round(h * aspect))
        tiles = [Image.fromarray((f * 255).astype(np.uint8)).resize((w, h2), Image.BILINEAR) for f in frames]
        rows = math.ceil(FRAMES / COLS)
        sheet = Image.new("L", (w * COLS, h2 * rows), 0)
        for i, t in enumerate(tiles):
            sheet.paste(t, ((i % COLS) * w, (i // COLS) * h2))
        sheet.save(VOL / study_id / "mip.png", optimize=True)
        sj = VOL / study_id / "study.json"
        study = json.loads(sj.read_text())
        study["mip"] = {
            "sprite": f"{study_id}/mip.png", "frames": FRAMES, "cols": COLS, "frameWidth": w, "frameHeight": h2,
            "label": label, "colormap": cmap, "bytes": (VOL / study_id / "mip.png").stat().st_size,
        }
        sj.write_text(json.dumps(study, indent=2))
        print(study_id, f"{w}x{h2}", round((VOL / study_id / 'mip.png').stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
