"""Fetal brain, 21 to 36 weeks (dHCP spatio-temporal fetal brain MRI atlas, Uus et al. 2023, CC0).

One 3D T2-weighted template per gestational week at 0.5 mm, averaged from motion-corrected in-utero MRI of 187
fetuses, with the 19-label BOUNTI tissue parcellation. The atlas stores every week scaled to one common size;
each week's MIRTK affine (`transformations/affine-NN.dof`) is undone here so the brain grows on the timeline.
All weeks are resampled onto one shared world grid, so the viewer's camera stays fixed while the brain grows.

Input : work/fetal_dhcp/{structural/t2-tNN.00.nii.gz, parcellations/tissue-tNN.00_dhcp-19.nii.gz,
        transformations/affine-NN.dof, info/...}  from https://gin.g-node.org/kcl_cdb/fetal_brain_mri_atlas
Output: work/volumes/fetal-brain-atlas/week-NN/{t2.nii.gz,tissue.nii.gz}, tissue.lut.json, thumbnail.jpg, study.json
"""
import json
import pathlib
import shutil
import struct

import nibabel as nib
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "fetal_dhcp"
OUT = ROOT / "work" / "volumes" / "fetal-brain-atlas"
STUDY_ID = "fetal-brain-atlas"
WEEKS = range(21, 37)
SPACING = 0.5
MARGIN_MM = 3.0

# BOUNTI labels -> display name, colour, alpha. Left and right share a colour. External CSF is hidden so the cortex
# shows in 3D; it takes the cortex colour so interpolation at the hidden edge does not tint the sulci.
TISSUE = {
    1: ("External CSF", "#e8846b", 0), 2: ("External CSF", "#e8846b", 0),
    3: ("Cortical grey matter", "#e8846b", 255), 4: ("Cortical grey matter", "#e8846b", 255),
    5: ("White matter", "#f4e2c6", 255), 6: ("White matter", "#f4e2c6", 255),
    7: ("Lateral ventricles", "#4f9fe0", 255), 8: ("Lateral ventricles", "#4f9fe0", 255),
    9: ("Cavum septum pellucidum", "#7cc0f0", 255),
    10: ("Brainstem", "#b88ad8", 255),
    11: ("Cerebellum", "#5fbf86", 255), 12: ("Cerebellum", "#5fbf86", 255),
    13: ("Cerebellar vermis", "#3f9e6a", 255),
    14: ("Basal ganglia", "#f2c14e", 255), 15: ("Basal ganglia", "#f2c14e", 255),
    16: ("Thalamus", "#d9577a", 255), 17: ("Thalamus", "#d9577a", 255),
    18: ("Third and fourth ventricles", "#3a86c8", 255), 19: ("Third and fourth ventricles", "#3a86c8", 255),
}
BRAIN_LABELS = list(range(3, 20))  # everything inside the external CSF


def read_scale(week: int) -> np.ndarray:
    """MIRTK binary affine: magic, type, n=12, then tx ty tz rx ry rz sx sy sz (percent) and skews as big-endian doubles."""
    raw = (SRC / "transformations" / f"affine-{week}.dof").read_bytes()
    _, _, n = struct.unpack(">III", raw[:12])
    p = struct.unpack(f">{n}d", raw[12:12 + 8 * n])
    if any(abs(v) > 1e-6 for v in p[:6] + p[9:]):
        raise ValueError(f"week {week}: only pure scaling is supported, got {p}")
    return np.array(p[6:9]) / 100.0


def lut() -> dict:
    out = {"R": [0], "G": [0], "B": [0], "A": [0], "I": [0], "labels": [""]}
    for i, (name, hexc, alpha) in TISSUE.items():
        out["I"].append(i)
        for k, v in zip("RGB", (int(hexc[j:j + 2], 16) for j in (1, 3, 5))):
            out[k].append(v)
        out["A"].append(alpha)
        out["labels"].append(name)
    return out


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    table = lut()
    (OUT / "tissue.lut.json").write_text(json.dumps(table))

    # The atlas maps world -> atlas space by scaling about the origin: atlas = S * world.
    src = {}
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for w in WEEKS:
        t2 = nib.load(SRC / "structural" / f"t2-t{w}.00.nii.gz")
        s = read_scale(w)
        data = np.asarray(t2.dataobj, np.float32)
        idx = np.argwhere(data > 0)
        corners = np.array([[a, b, c, 1] for a in (idx[:, 0].min(), idx[:, 0].max())
                            for b in (idx[:, 1].min(), idx[:, 1].max()) for c in (idx[:, 2].min(), idx[:, 2].max())])
        world = (t2.affine @ corners.T)[:3].T / s
        lo, hi = np.minimum(lo, world.min(0)), np.maximum(hi, world.max(0))
        src[w] = (t2, s)
    lo -= MARGIN_MM
    hi += MARGIN_MM
    shape = tuple(int(np.ceil(v)) for v in (hi - lo) / SPACING)
    # RAS grid with x running right-to-left like the source, so slices keep the radiological orientation.
    out_aff = np.diag([-SPACING, SPACING, SPACING, 1.0])
    out_aff[:3, 3] = [hi[0], lo[1], lo[2]]
    print("grid", shape, "mm", np.round(hi - lo, 1))

    frames, raw_files, raw_bytes, cache = [], 0, 0, {}
    for w in WEEKS:
        t2_img, s = src[w]
        lab_path = SRC / "parcellations" / f"tissue-t{w}.00_dhcp-19.nii.gz"
        lab_img = nib.load(lab_path)
        m = np.linalg.inv(t2_img.affine) @ np.diag([*s, 1.0]) @ out_aff
        t2 = ndimage.affine_transform(np.asarray(t2_img.dataobj, np.float32), m[:3, :3], m[:3, 3], output_shape=shape,
                                      order=3, mode="constant", cval=0.0)
        lab = ndimage.affine_transform(np.asarray(lab_img.dataobj, np.uint8), m[:3, :3], m[:3, 3], output_shape=shape,
                                       order=0, mode="constant", cval=0)
        t2[(t2 < 0) | (lab == 0)] = 0  # cubic ringing outside the brain
        # Same white-matter brightness every week, so the display window holds across the timeline.
        wm = t2[np.isin(lab, (5, 6))]
        t2 = np.clip(t2 * (400.0 / float(np.median(wm))), 0, 4000)
        d = OUT / f"week-{w}"
        d.mkdir()
        nib.save(nib.Nifti1Image(np.rint(t2).astype(np.int16), out_aff), d / "t2.nii.gz")
        li = nib.Nifti1Image(lab, out_aff)
        li.header.set_intent("label")
        nib.save(li, d / "tissue.nii.gz")
        brain_ml = float(np.isin(lab, BRAIN_LABELS).sum() * SPACING ** 3 / 1000)
        cache[w] = (t2, lab)
        for f in (SRC / "structural" / f"t2-t{w}.00.nii.gz", lab_path, SRC / "transformations" / f"affine-{w}.dof"):
            raw_files += 1
            raw_bytes += f.stat().st_size
        frames.append({
            "value": w,
            "label": f"{w} weeks",
            "brainVolumeMl": round(brain_ml, 1),
            "note": f"brain {brain_ml:,.0f} ml",
            "layers": {"t2": f"{STUDY_ID}/week-{w}/t2.nii.gz", "tissue": f"{STUDY_ID}/week-{w}/tissue.nii.gz"},
            "bytes": (d / "t2.nii.gz").stat().st_size + (d / "tissue.nii.gz").stat().st_size,
        })
        print(f"week {w}: scale {np.round(s, 3)}  brain {brain_ml:6.1f} ml", flush=True)
    for f in ("README.md", "LICENSE", "datacite.yml"):
        if (SRC / f).exists():
            raw_files += 1
            raw_bytes += (SRC / f).stat().st_size

    # Thumbnail: axial slices at 21, 28 and 36 weeks on the shared grid, so the growth is to scale.
    rgb_of = np.zeros((256, 3))
    for i, r, g, b in zip(table["I"], table["R"], table["G"], table["B"]):
        rgb_of[i] = (r, g, b)
    z = int(np.argmax(np.isin(cache[36][1], (16, 17)).sum(axis=(0, 1))))  # through the thalami
    ys, xs = np.nonzero(np.rot90(cache[36][0][:, :, z]) > 0)
    box = (xs.min() - 4, ys.min() - 4, xs.max() + 5, ys.max() + 5)  # largest brain; the others sit inside it
    tiles = []
    for w in (21, 28, 36):
        t2, lab = cache[w]
        sl = np.clip(t2[:, :, z] / 900.0, 0, 1)[..., None] * 255
        col = rgb_of[lab[:, :, z]]
        show = (lab[:, :, z] > 2)[..., None]
        rgb = np.where(show, 0.5 * sl + 0.5 * col, sl)
        rgb = np.where((t2[:, :, z] > 0)[..., None], rgb, 255)
        tiles.append(Image.fromarray(np.rot90(rgb).astype(np.uint8)).crop(box))
    gap = tiles[0].width // 12
    canvas = Image.new("RGB", (tiles[0].width * 3 + gap * 2, tiles[0].height), (255, 255, 255))
    for i, t in enumerate(tiles):
        canvas.paste(t, (i * (t.width + gap), 0))
    canvas.thumbnail((512, 512), Image.LANCZOS)
    thumb = Image.new("RGB", (512, 512), (255, 255, 255))
    thumb.paste(canvas, ((512 - canvas.width) // 2, (512 - canvas.height) // 2))
    thumb.save(OUT / "thumbnail.jpg", quality=90)

    growth = frames[-1]["brainVolumeMl"] / frames[0]["brainVolumeMl"]
    study = {
        "id": STUDY_ID,
        "category": "Fetal",
        "title": "Fetal brain development, 21 to 36 weeks",
        "subtitle": "4D MRI atlas, one 3D volume per gestational week",
        "modality": "Fetal MRI (T2-weighted), spatiotemporal atlas",
        "description": (
            "A normative atlas of the developing fetal brain at 0.5 mm, averaged from motion-corrected in-utero MRI of 187 "
            "pregnancies in the developing Human Connectome Project. Press Play to watch the smooth brain of the second "
            f"trimester fold into gyri and sulci as its volume grows {growth:.1f}-fold. Turn on Tissue labels to colour the "
            "cortex, white matter, ventricles, deep grey matter and cerebellum, or turn off the T2 layer to see the labelled "
            "brain on its own."
        ),
        "source": "developing Human Connectome Project (dHCP), King's College London, fetal brain MRI atlas, via G-Node GIN",
        "sourceUrl": "https://gin.g-node.org/kcl_cdb/fetal_brain_mri_atlas",
        "license": "CC0 1.0 (public domain dedication)",
        "citation": (
            "Uus A, Kyriakopoulou V, Cordero Grande L, et al. Multi-channel spatio-temporal MRI atlas of the normal fetal "
            "brain development from the developing Human Connectome Project. G-Node, 2023. "
            "https://doi.org/10.12751/g-node.ysgsy1. Tissue labels: Uus AU, et al. BOUNTI, eLife 12:RP88818 (2023)."
        ),
        "subject": "Atlas built from 187 fetuses without reported anomalies (21 to 37 weeks gestational age)",
        "thumbnail": f"{STUDY_ID}/thumbnail.jpg",
        "rawPath": f"raw/volumes/{STUDY_ID}/",
        "rawFiles": raw_files,
        "rawSizeBytes": raw_bytes,
        "defaultView": "render",
        "defaultPreset": "solid",
        "defaultClip": {"on": True, "depth": 0.1, "face": "front"},
        "stats": {"weeks": len(frames), "brainVolumeMlStart": frames[0]["brainVolumeMl"], "brainVolumeMlEnd": frames[-1]["brainVolumeMl"]},
        "layers": [
            # Fixed window: intensities are normalised to white matter = 400, so it holds for every week.
            {"id": "t2", "label": "T2 MRI", "kind": "mri", "frameKey": "t2", "calMin": 0, "calMax": 850},
            {"id": "tissue", "label": "Tissue labels", "kind": "labels", "frameKey": "tissue",
             "lut": f"{STUDY_ID}/tissue.lut.json", "opacity": 1.0, "visible": False},
        ],
        "timeline": {"label": "Gestational age", "unit": "weeks", "initial": 30, "frames": frames},
        "dims": list(shape),
        "spacingMm": [SPACING] * 3,
    }
    (OUT / "study.json").write_text(json.dumps(study, indent=2))
    print(len(frames), "weeks", frames[0]["brainVolumeMl"], "->", frames[-1]["brainVolumeMl"], "ml", shape,
          f"{sum(f['bytes'] for f in frames) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
