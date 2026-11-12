"""Fetal body growth, 22 to 38 weeks (KCL 0.55T fetal body MRI atlas, Uus et al. 2024, CC0).

One 3D T2-weighted volume of the fetal trunk per gestational week at 0.7 mm, averaged from motion-corrected
in-utero MRI of 106 healthy fetuses, with nine organ labels. All weeks share one grid in real-world size, so the
body grows on the timeline. The atlas header carries an oblique scanner tilt; volumes are snapped to the body's
own axes so the fetus stands upright in the viewer.

Input : work/fetal_body/{t2w-body/t2w-NN.nii.gz, body-organ-labels/labels/label-t2w-NN.nii.gz, ...}
        from https://gin.g-node.org/kcl_cdb/055t_fetal_mri_atlases
Output: work/volumes/fetal-body-atlas/week-NN/{t2.nii.gz,organs.nii.gz}, organs.lut.json, thumbnail.jpg, study.json
"""
import json
import pathlib
import shutil

import nibabel as nib
import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "fetal_body"
OUT = ROOT / "work" / "volumes" / "fetal-body-atlas"
STUDY_ID = "fetal-body-atlas"
WEEKS = range(22, 39)

# Label ids from the atlas centile workbook (body-organ-MRI-centiles-055t.xlsx).
ORGANS = {
    1: ("Lungs", "#f4b6c8"),
    2: ("Liver", "#b4552a"),
    3: ("Stomach", "#7fc3df"),
    4: ("Spleen", "#7b3fa0"),
    5: ("Renal pelvis", "#f6e27a"),
    6: ("Kidneys", "#c25a9e"),
    7: ("Bladder", "#f2c14e"),
    8: ("Thymus", "#e8a0d8"),
    9: ("Gallbladder", "#5fbf86"),
}


def upright(img: nib.Nifti1Image) -> nib.Nifti1Image:
    """Snap the oblique header to the nearest anatomical axes, then reorder the data to RAS."""
    ornt = nib.orientations.io_orientation(img.affine)
    zooms = img.header.get_zooms()[:3]
    aff = np.eye(4)
    aff[:3, :3] = 0
    for i, (axis, flip) in enumerate(ornt):
        aff[int(axis), i] = flip * zooms[i]
    aff[:3, 3] = -aff[:3, :3] @ ((np.array(img.shape[:3]) - 1) / 2)
    return nib.as_closest_canonical(nib.Nifti1Image(np.asanyarray(img.dataobj), aff))


def lut() -> dict:
    out = {"R": [0], "G": [0], "B": [0], "A": [0], "I": [0], "labels": [""]}
    for i, (name, hexc) in ORGANS.items():
        out["I"].append(i)
        for k, j in zip("RGB", (1, 3, 5)):
            out[k].append(int(hexc[j:j + 2], 16))
        out["A"].append(255)
        out["labels"].append(name)
    return out


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    table = lut()
    (OUT / "organs.lut.json").write_text(json.dumps(table))

    frames, cache, raw_files, raw_bytes = [], {}, 0, 0
    for w in WEEKS:
        t2_path = SRC / "t2w-body" / f"t2w-{w}.nii.gz"
        lab_path = SRC / "body-organ-labels" / "labels" / f"label-t2w-{w}.nii.gz"
        t2 = upright(nib.load(t2_path))
        lab = upright(nib.load(lab_path))
        t2d = np.asarray(t2.dataobj).astype(np.int16)
        labd = np.rint(np.asarray(lab.dataobj)).astype(np.uint8)
        d = OUT / f"week-{w}"
        d.mkdir()
        nib.save(nib.Nifti1Image(t2d, t2.affine), d / "t2.nii.gz")
        li = nib.Nifti1Image(labd, lab.affine)
        li.header.set_intent("label")
        nib.save(li, d / "organs.nii.gz")
        vox_ml = float(np.prod(t2.header.get_zooms()[:3])) / 1000
        vol = {name: float((labd == i).sum() * vox_ml) for i, (name, _) in ORGANS.items()}
        cache[w] = (t2d, labd)
        for f in (t2_path, lab_path):
            raw_files += 1
            raw_bytes += f.stat().st_size
        frames.append({
            "value": w,
            "label": f"{w} weeks",
            "note": f"lungs {vol['Lungs']:,.0f} ml · liver {vol['Liver']:,.0f} ml",
            "lungVolumeMl": round(vol["Lungs"], 1),
            "liverVolumeMl": round(vol["Liver"], 1),
            "layers": {"t2": f"{STUDY_ID}/week-{w}/t2.nii.gz", "organs": f"{STUDY_ID}/week-{w}/organs.nii.gz"},
            "bytes": (d / "t2.nii.gz").stat().st_size + (d / "organs.nii.gz").stat().st_size,
        })
        print(f"week {w}: lungs {vol['Lungs']:5.1f}  liver {vol['Liver']:5.1f}", flush=True)
    for f in ("README.md", "LICENSE", "centiles/body-organ-MRI-centiles-055t.xlsx", "info/055t-body.jpg"):
        if (SRC / f).exists():
            raw_files += 1
            raw_bytes += (SRC / f).stat().st_size

    # Thumbnail: coronal slices at 22, 30 and 38 weeks through the kidneys, organs over T2, to scale.
    rgb_of = np.zeros((256, 3))
    for i, r, g, b in zip(table["I"], table["R"], table["G"], table["B"]):
        rgb_of[i] = (r, g, b)
    t38, l38 = cache[38]
    y = int(np.argmax((l38 == 6).sum(axis=(0, 2))))
    top = float(np.percentile(t38[t38 > 0], 99))
    sl = np.rot90(t38[:, y, :] > 0)
    rows, cols = np.nonzero(sl)
    box = (cols.min() - 3, rows.min() - 3, cols.max() + 4, rows.max() + 4)
    tiles = []
    for w in (22, 30, 38):
        t2d, labd = cache[w]
        y = int(np.argmax((labd == 6).sum(axis=(0, 2))))
        g = np.clip(t2d[:, y, :] / top, 0, 1)[..., None] * 255
        col = rgb_of[labd[:, y, :]]
        rgb = np.where((labd[:, y, :] > 0)[..., None], 0.35 * g + 0.65 * col, g)
        rgb = np.where((t2d[:, y, :] > 0)[..., None], rgb, 255)
        tiles.append(Image.fromarray(np.rot90(rgb).astype(np.uint8)).crop(box))
    gap = tiles[0].width // 10
    canvas = Image.new("RGB", (tiles[0].width * 3 + gap * 2, tiles[0].height), (255, 255, 255))
    for i, t in enumerate(tiles):
        canvas.paste(t, (i * (t.width + gap), 0))
    canvas.thumbnail((512, 512), Image.LANCZOS)
    thumb = Image.new("RGB", (512, 512), (255, 255, 255))
    thumb.paste(canvas, ((512 - canvas.width) // 2, (512 - canvas.height) // 2))
    thumb.save(OUT / "thumbnail.jpg", quality=90)

    t2 = nib.load(OUT / "week-30" / "t2.nii.gz")
    lungs_x = frames[-1]["lungVolumeMl"] / frames[0]["lungVolumeMl"]
    study = {
        "id": STUDY_ID,
        "category": "Fetal",
        "title": "Fetal body growth, 22 to 38 weeks",
        "subtitle": "4D MRI atlas of the trunk with organ labels",
        "modality": "Fetal MRI (T2-weighted), body atlas",
        "description": (
            "The chest and abdomen of a baby before birth, averaged from motion-corrected MRI of 106 healthy pregnancies: "
            "one 3D volume for every week from 22 to 38. The organs are outlined in colour: lungs, liver, stomach, kidneys, "
            f"bladder, thymus, spleen and gallbladder. Press Play to watch them grow; the lungs grow {lungs_x:.1f}-fold."
        ),
        "source": "King's College London, 0.55T fetal MRI atlases (Uus et al.), via G-Node GIN",
        "sourceUrl": "https://gin.g-node.org/kcl_cdb/055t_fetal_mri_atlases",
        "license": "CC0 1.0 (public domain dedication)",
        "citation": (
            "Uus A, Aviles Verdera J, Payette K, et al. Normative growth models for T2w 0.55T fetal brain and body MRI: "
            "population-averaged 4D atlases and volumetry centiles. ISMRM 2024, abstract 0819. Organ labels: Uus AU, Hall M, "
            "et al. Sci Rep 14, 6637 (2024). https://doi.org/10.1038/s41598-024-57087-x"
        ),
        "subject": "Atlas built from 106 healthy fetuses (22 to 38 weeks gestational age), 0.55 T MRI",
        "thumbnail": f"{STUDY_ID}/thumbnail.jpg",
        "rawPath": f"raw/volumes/{STUDY_ID}/",
        "rawFiles": raw_files,
        "rawSizeBytes": raw_bytes,
        "defaultView": "render",
        "defaultPreset": "solid",
        "defaultClip": {"on": True, "depth": 0.0, "face": "front"},
        "stats": {
            "weeks": len(frames),
            "organs": len(ORGANS),
            "lungVolumeMlStart": frames[0]["lungVolumeMl"],
            "lungVolumeMlEnd": frames[-1]["lungVolumeMl"],
        },
        "layers": [
            {"id": "t2", "label": "T2 MRI", "kind": "mri", "frameKey": "t2", "calMin": 0, "calMax": 1800},
            {"id": "organs", "label": "Organ labels", "kind": "labels", "frameKey": "organs",
             "lut": f"{STUDY_ID}/organs.lut.json", "opacity": 1.0, "visible": True},
        ],
        "timeline": {"label": "Gestational age", "unit": "weeks", "initial": 30, "frames": frames},
        "dims": list(t2.shape[:3]),
        "spacingMm": [round(float(z), 2) for z in t2.header.get_zooms()[:3]],
    }
    (OUT / "study.json").write_text(json.dumps(study, indent=2))
    print(len(frames), "weeks", study["dims"], f"{sum(f['bytes'] for f in frames) / 1e6:.1f} MB", f"lungs x{lungs_x:.1f}")


if __name__ == "__main__":
    main()
