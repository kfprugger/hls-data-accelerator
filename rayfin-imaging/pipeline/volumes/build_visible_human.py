"""Visible Human Female (NLM, public domain) -> true-colour RGBA NIfTI volumes for NiiVue.

Input : work/vhp/png/avfNNNN{a,b,c}.png  (5,186 axial cryosection photographs, 2048 x 1216, 0.33 mm)
Output: work/volumes/visible-human-body/{body.nii.gz,thumbnail.jpg,study.json}   whole body, 2 mm
        work/volumes/visible-human-head/{head.nii.gz,thumbnail.jpg,study.json}   head and neck, 1 mm

The blue gelatin the specimen was frozen in is made transparent (alpha = 0) so the body renders in
its own colours. Orientation: image column -> patient left, image row -> anterior, slice -> inferior.
"""
import json
import multiprocessing as mp
import os
import pathlib
import re

import nibabel as nib
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "vhp" / "png"
OUT = ROOT / "work" / "volumes"
STACK = ROOT / "work" / "vhp" / "stack_1mm"
F = 3  # 0.33 mm -> 1 mm
PX_MM = 0.33 * F
ROW_LIMIT = 980 // F  # rows below this are the grey scale strip and slice labels, outside the gel
H, W = 1215 // F, 2046 // F

SOURCE = {
    "source": "U.S. National Library of Medicine, Visible Human Project (Visible Human Female)",
    "sourceUrl": "https://www.nlm.nih.gov/research/visible/visible_human.html",
    "license": "Public domain (NLM Terms and Conditions, no licence agreement required since 2019)",
    "citation": "U.S. National Library of Medicine. The Visible Human Project. https://www.nlm.nih.gov/research/visible/",
}


def slice_groups() -> list[list[pathlib.Path]]:
    files = sorted(SRC.glob("avf*.png"), key=lambda p: (int(re.findall(r"\d+", p.name)[0]), p.name))
    by_mm: dict[int, list[pathlib.Path]] = {}
    for f in files:
        by_mm.setdefault(int(re.findall(r"\d+", f.name)[0]), []).append(f)
    return [by_mm[k] for k in sorted(by_mm)]


def load_group(paths: list[pathlib.Path]) -> tuple[np.ndarray, np.ndarray]:
    acc = np.zeros((H, W, 3), np.float32)
    n = 0
    for p in paths:
        if p.stat().st_size == 0:
            continue  # two empty source files in the NLM archive (avf2100a/b)
        a = np.asarray(Image.open(p).convert("RGB"), np.float32)[: H * F, : W * F]
        acc += a.reshape(H, F, W, F, 3).mean(axis=(1, 3))
        n += 1
    rgb = acc / max(n, 1)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    warm = (r > b + 12) & (r + g + b > 90)
    warm[ROW_LIMIT:] = False
    warm = ndimage.binary_opening(warm, iterations=1)
    mask = ndimage.binary_fill_holes(warm)
    lab, k = ndimage.label(mask)
    if k:
        idx = range(1, k + 1)
        sizes = ndimage.sum(mask, lab, idx)
        red, green = ndimage.mean(r, lab, idx), ndimage.mean(g, lab, idx)
        # Slice labels are pale yellow-green paper (green >= red); every tissue is red-dominant.
        keep = (sizes >= 150) & (np.asarray(red) > np.asarray(green) + 2)
        mask = np.isin(lab, 1 + np.flatnonzero(keep))
    return rgb.clip(0, 255).astype(np.uint8), mask


def _work(args):
    i, paths = args
    rgb, mask = load_group(paths)
    return i, rgb, mask


def build_stack() -> tuple[np.ndarray, np.ndarray]:
    groups = slice_groups()
    STACK.mkdir(parents=True, exist_ok=True)
    rgb_path, mask_path = STACK / "rgb.u8", STACK / "mask.u8"
    shape = (len(groups), H, W)
    if rgb_path.exists() and mask_path.exists():
        return (
            np.memmap(rgb_path, np.uint8, "r", shape=shape + (3,)),
            np.memmap(mask_path, np.uint8, "r", shape=shape),
        )
    rgb = np.memmap(rgb_path, np.uint8, "w+", shape=shape + (3,))
    mask = np.memmap(mask_path, np.uint8, "w+", shape=shape)
    with mp.Pool(max(1, (os.cpu_count() or 4) - 2)) as pool:
        for n, (i, r, m) in enumerate(pool.imap_unordered(_work, enumerate(groups), chunksize=4)):
            rgb[i], mask[i] = r, m
            if n % 200 == 0:
                print(f"  {n}/{len(groups)} mm", flush=True)
    rgb.flush()
    mask.flush()
    return rgb, mask


def clean_mask_3d(mask: np.ndarray) -> np.ndarray:
    """Keep the body (and limbs) and drop stray specks, judged on a 4 mm grid."""
    z, y, x = (s // 4 for s in mask.shape)
    coarse = mask[: z * 4, : y * 4, : x * 4].reshape(z, 4, y, 4, x, 4).max(axis=(1, 3, 5))
    lab, k = ndimage.label(coarse)
    sizes = ndimage.sum(coarse, lab, range(1, k + 1))
    keep = np.isin(lab, 1 + np.flatnonzero(sizes >= 0.03 * sizes.max()))
    keep = np.repeat(np.repeat(np.repeat(keep, 4, 0), 4, 1), 4, 2)
    out = np.zeros_like(mask, dtype=bool)
    out[: z * 4, : y * 4, : x * 4] = keep
    return out & mask.astype(bool)


def to_rgba(rgb: np.ndarray, mask: np.ndarray, factor: int) -> np.ndarray:
    """Mask-weighted block average so gel colour never bleeds into tissue edges; soft alpha."""
    z, y, x = (s // factor for s in mask.shape)
    m = mask[: z * factor, : y * factor, : x * factor].astype(np.float32)
    c = rgb[: z * factor, : y * factor, : x * factor].astype(np.float32)
    msum = m.reshape(z, factor, y, factor, x, factor).sum(axis=(1, 3, 5))
    csum = (c * m[..., None]).reshape(z, factor, y, factor, x, factor, 3).sum(axis=(1, 3, 5))
    color = csum / np.maximum(msum, 1)[..., None]
    alpha = msum / factor**3
    rgba = np.concatenate([color, (alpha * 255)[..., None]], axis=-1)
    rgba[alpha < 0.15] = 0
    return rgba.clip(0, 255).astype(np.uint8)


def repair_block_gaps(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The cadaver was cut into four blocks before sectioning; interpolate the few lost millimetres."""
    area = mask.reshape(len(mask), -1).sum(axis=1).astype(float)
    med = ndimage.median_filter(area, size=15)
    bad = (area < 0.95 * med) & (med > 500)
    # Treat one section either side of each gap as damaged too (partial cuts, exposure change).
    bad = ndimage.binary_dilation(bad, iterations=1)
    good = np.flatnonzero(~bad)
    rgb, mask = np.array(rgb), np.array(mask)
    for z in np.flatnonzero(bad):
        before, after = good[good < z], good[good > z]
        if len(before) == 0 or len(after) == 0:
            continue  # first or last section: nothing to interpolate from
        lo, hi = before.max(), after.min()
        t = (z - lo) / (hi - lo)
        rgb[z] = ((1 - t) * rgb[lo] + t * rgb[hi]).astype(np.uint8)
        mask[z] = mask[lo] | mask[hi]
    print(f"interpolated {int(bad.sum())} block-boundary sections", flush=True)
    return rgb, mask


def bbox(mask: np.ndarray, margin: int = 4) -> tuple[slice, slice, slice]:
    idx = [np.flatnonzero(mask.any(axis=tuple(a for a in range(3) if a != d))) for d in range(3)]
    return tuple(slice(max(0, i[0] - margin), min(mask.shape[d], i[-1] + 1 + margin)) for d, i in enumerate(idx))


def save_rgba(rgba_zyx: np.ndarray, spacing: float, path: pathlib.Path) -> None:
    # (z, row, col, 4) -> (col, row, z): i -> patient left (-x), j -> anterior (+y), k -> inferior (-z)
    data = np.ascontiguousarray(rgba_zyx.transpose(2, 1, 0, 3))
    rec = data.view([("R", "u1"), ("G", "u1"), ("B", "u1"), ("A", "u1")]).reshape(data.shape[:3])
    nx, ny, nz = rec.shape
    affine = np.diag([-spacing, spacing, -spacing, 1.0])
    affine[:3, 3] = [spacing * nx / 2, -spacing * ny / 2, spacing * nz / 2]
    img = nib.Nifti1Image(rec, affine)
    img.header.set_xyzt_units("mm")
    img.header.set_qform(affine, 1)
    img.header.set_sform(affine, 1)
    nib.save(img, path)


def coronal_thumbnail(rgba_zyx: np.ndarray, path: pathlib.Path, size: int = 512) -> None:
    """A coronal section through the middle of the body, in true colour on white."""
    rows = (rgba_zyx[..., 3] > 96).sum(axis=(0, 2))
    mid = int(np.argmax(rows))
    sl = rgba_zyx[:, max(0, mid - 1): mid + 2].astype(np.float32).mean(axis=1)  # 3-voxel slab
    alpha = sl[..., 3:4] / 255.0
    color = sl[..., :3] * alpha + 255 * (1 - alpha)
    img = Image.fromarray(color.clip(0, 255).astype(np.uint8)[:, ::-1])  # patient right on image left
    img.thumbnail((size, size))
    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    canvas.save(path, "JPEG", quality=88)


def write_study(study_id: str, study: dict) -> None:
    (OUT / study_id / "study.json").write_text(json.dumps(study, indent=2))


def main() -> None:
    print("Reducing 0.33 mm sections to a 1 mm colour stack...", flush=True)
    rgb, mask = build_stack()
    print("stack", rgb.shape, flush=True)
    rgb, mask = repair_block_gaps(rgb, clean_mask_3d(np.asarray(mask)))
    # Drop the outermost ring of tissue pixels, which are blended with the blue gel.
    mask = ndimage.binary_erosion(mask, structure=np.ones((1, 3, 3), bool))
    raw_bytes = sum(p.stat().st_size for p in SRC.glob("avf*.png"))
    n_sections = len(list(SRC.glob("avf*.png")))

    # Whole body, 2 mm.
    zs, ys, xs = bbox(mask, margin=6)
    body = to_rgba(rgb[zs, ys, xs], mask[zs, ys, xs], 2)
    d = OUT / "visible-human-body"
    d.mkdir(parents=True, exist_ok=True)
    save_rgba(body, 2 * PX_MM, d / "body.nii.gz")
    coronal_thumbnail(body, d / "thumbnail.jpg")
    print("body", body.shape, (d / "body.nii.gz").stat().st_size / 1e6, "MB", flush=True)
    write_study("visible-human-body", {
        "id": "visible-human-body",
        "category": "Whole body",
        "title": "Visible Human Female, whole body",
        "subtitle": "True-colour cryosection volume, 2 mm",
        "modality": "Cryosection photography (RGB)",
        "description": (
            "A complete female body reconstructed from 5,186 colour photographs of cryosections taken at 0.33 mm "
            "intervals. Every voxel is the real colour of the tissue: yellow fat, red muscle, grey-white brain. "
            "It opens cut down the middle; drag the clip slider to move the cut through the body, or switch to side or top."
        ),
        **SOURCE,
        "subject": "Female, 59 years, cadaver (donated)",
        "thumbnail": "visible-human-body/thumbnail.jpg",
        "rawPath": "raw/volumes/visible-human-female/png/",
        "rawFiles": n_sections,
        "rawSizeBytes": raw_bytes,
        "defaultView": "render",
        "defaultClip": {"on": True, "depth": 0.0, "face": "front"},
        "layers": [{
            "id": "rgb", "label": "Cryosection colour", "file": "visible-human-body/body.nii.gz",
            "kind": "rgba", "bytes": (d / "body.nii.gz").stat().st_size,
        }],
        "dims": list(body.shape[2::-1]),
        "spacingMm": [round(2 * PX_MM, 3)] * 3,
    })

    # Head and neck, 1 mm: from the vertex to 280 mm down.
    top = zs.start
    head_z = slice(top, min(top + 280, mask.shape[0]))
    hm = mask[head_z]
    _, hy, hx = bbox(hm, margin=6)
    head = to_rgba(rgb[head_z, hy, hx], hm[:, hy, hx], 1)
    d = OUT / "visible-human-head"
    d.mkdir(parents=True, exist_ok=True)
    save_rgba(head, PX_MM, d / "head.nii.gz")
    coronal_thumbnail(head, d / "thumbnail.jpg")
    print("head", head.shape, (d / "head.nii.gz").stat().st_size / 1e6, "MB", flush=True)
    write_study("visible-human-head", {
        "id": "visible-human-head",
        "category": "Whole body",
        "title": "Visible Human Female, head and neck",
        "subtitle": "True-colour cryosection volume, 1 mm",
        "modality": "Cryosection photography (RGB)",
        "description": (
            "The head and neck of the Visible Human Female at 1 mm, opened along the midline: brain, cerebellum, "
            "tongue, airway and spinal cord in their natural colours. Move the cut with the clip slider."
        ),
        **SOURCE,
        "subject": "Female, 59 years, cadaver (donated)",
        "thumbnail": "visible-human-head/thumbnail.jpg",
        "rawPath": "raw/volumes/visible-human-female/png/",
        "rawFiles": n_sections,
        "rawSizeBytes": raw_bytes,
        "defaultView": "render",
        "defaultClip": {"on": True, "depth": 0.0, "face": "side"},
        "layers": [{
            "id": "rgb", "label": "Cryosection colour", "file": "visible-human-head/head.nii.gz",
            "kind": "rgba", "bytes": (d / "head.nii.gz").stat().st_size,
        }],
        "dims": list(head.shape[2::-1]),
        "spacingMm": [round(PX_MM, 3)] * 3,
    })


if __name__ == "__main__":
    main()
