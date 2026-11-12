"""Fetal face and head (KCL craniofacial fetal MRI atlas, Matthew et al. 2024, CC0).

A 0.5 mm T2-weighted MRI atlas of the fetal head averaged from 12 normal fetuses (20 to 36 weeks), with a head mask
and 45 craniofacial landmarks. The amniotic fluid around the head is removed with a slightly smoothed head mask so
3D rendering shows the skin surface: the face, as parents see it on a 3D ultrasound.

Input : work/fetal_face/{fetal-t2w-head-atlas, fetal-t2w-head-label, fetal-t2w-head-landmarks}.nii.gz,
        craniofacial_labels.txt  from https://gin.g-node.org/kcl_cdb/craniofacial_fetal_mri_atlas
Output: work/volumes/fetal-face-atlas/{t2.nii.gz, landmarks.nii.gz, landmarks.lut.json, thumbnail.jpg, study.json}
"""
import json
import pathlib
import re
import shutil

import nibabel as nib
import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "fetal_face"
OUT = ROOT / "work" / "volumes" / "fetal-face-atlas"
STUDY_ID = "fetal-face-atlas"
MARGIN = 6


def landmark_lut() -> dict:
    out = {"R": [0], "G": [0], "B": [0], "A": [0], "I": [0], "labels": [""]}
    for line in (SRC / "craniofacial_labels.txt").read_text().splitlines():
        m = re.match(r'\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+[\d.]+\s+\d\s+\d\s+"(.*)"', line)
        if not m or m.group(1) == "0":
            continue
        idx, r, g, b, name = m.groups()
        out["I"].append(int(idx))
        out["R"].append(int(r))
        out["G"].append(int(g))
        out["B"].append(int(b))
        out["A"].append(255)
        # "Nose tip-NoT" -> "Nose tip"; fix the source's spelling slips.
        clean = re.split(r"[-_](?=[A-Z0-9][A-Za-z0-9]*$)", name)[0].strip()
        for a, b in (("Pharangeal", "pharyngeal"), ("formen", "foramen"), ("Palateal", "palatal"), ("Ant ", "anterior "),
                     ("Post ", "posterior "), ("Rt ", "right "), ("Lt ", "left "), ("ext ", "external "), ("Lat ", "lateral ")):
            clean = clean.replace(a, b)
        clean = clean.lower()
        out["labels"].append(clean[0].upper() + clean[1:])
    return out


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    img = nib.load(SRC / "fetal-t2w-head-atlas.nii.gz")
    t2 = np.asarray(img.dataobj).astype(np.float32)
    mask = np.asarray(nib.load(SRC / "fetal-t2w-head-label.nii.gz").dataobj) > 0
    marks = np.asarray(nib.load(SRC / "fetal-t2w-head-landmarks.nii.gz").dataobj).astype(np.uint8)

    # Smooth the mask edge so the rendered skin is a smooth surface rather than voxel steps.
    soft = ndimage.gaussian_filter(mask.astype(np.float32), 1.6)
    head = t2 * np.clip((soft - 0.2) / 0.6, 0, 1)

    idx = np.argwhere(mask)
    lo = np.maximum(idx.min(0) - MARGIN, 0)
    hi = np.minimum(idx.max(0) + MARGIN + 1, mask.shape)
    crop = tuple(slice(a, b) for a, b in zip(lo, hi))
    aff = img.affine.copy()
    aff[:3, 3] = img.affine[:3, :3] @ lo + img.affine[:3, 3]

    nib.save(nib.Nifti1Image(np.rint(head[crop]).astype(np.int16), aff), OUT / "t2.nii.gz")
    lm = nib.Nifti1Image(marks[crop], aff)
    lm.header.set_intent("label")
    nib.save(lm, OUT / "landmarks.nii.gz")
    lut = landmark_lut()
    (OUT / "landmarks.lut.json").write_text(json.dumps(lut))
    zooms = img.header.get_zooms()[:3]
    head_ml = float(mask.sum() * np.prod(zooms) / 1000)

    # Thumbnail: front view of the head surface, lit from the upper left, in the skin-tone colours used in 3D.
    # Sub-voxel depth from the front (the face looks towards +y): count the empty space along each ray.
    ray = np.clip((soft[crop][:, ::-1, :] - 0.3) / 0.4, 0, 1)
    filled = np.maximum.accumulate(ray, axis=1)
    has = filled[:, -1, :] > 0.5
    depth = (1 - filled).sum(axis=1)
    depth = ndimage.gaussian_filter(np.where(has, depth, depth[has].max() if has.any() else 0), 1.5)
    gx, gz = np.gradient(depth)
    normal = np.stack([-gx, np.ones_like(depth), -gz])
    normal /= np.linalg.norm(normal, axis=0, keepdims=True)
    light = np.array([-0.45, 0.8, 0.4])
    light /= np.linalg.norm(light)
    shade = np.clip((normal * light[:, None, None]).sum(0), 0, 1) ** 1.2
    tone = np.array([255, 214, 160]) * (0.25 + 0.75 * shade[..., None])
    rgb = np.where(has[..., None], tone, 255).astype(np.uint8)
    face = Image.fromarray(np.rot90(rgb))  # z up; image x is the head's x axis (radiological left on the right)
    face = face.crop(Image.eval(face.convert("L"), lambda v: 255 - v).getbbox())
    scale = 470 / max(face.size)
    face = face.resize((round(face.width * scale), round(face.height * scale)), Image.LANCZOS)
    thumb = Image.new("RGB", (512, 512), (255, 255, 255))
    thumb.paste(face, ((512 - face.width) // 2, (512 - face.height) // 2))
    thumb.save(OUT / "thumbnail.jpg", quality=90)

    raw = [SRC / f for f in ("fetal-t2w-head-atlas.nii.gz", "fetal-t2w-head-label.nii.gz", "fetal-t2w-head-landmarks.nii.gz",
                             "craniofacial_labels.txt", "README.md", "LICENSE") if (SRC / f).exists()]
    out_t2 = nib.load(OUT / "t2.nii.gz")
    study = {
        "id": STUDY_ID,
        "category": "Fetal",
        "title": "Fetal face and head, 3D MRI",
        "subtitle": "Craniofacial atlas at 0.5 mm",
        "modality": "Fetal MRI (T2-weighted), craniofacial atlas",
        "description": (
            "The face of a baby before birth, rebuilt in 3D from MRI taken through the mother's abdomen. Software corrects "
            "for the baby's movement and stacks the images into a 3D volume; this atlas averages 12 healthy fetuses. Drag to "
            "turn the head, or switch on Clip to cut through it and see the brain, eyes and airway inside."
        ),
        "source": "King's College London, craniofacial fetal MRI atlas (Matthew, Uus et al.), via G-Node GIN",
        "sourceUrl": "https://gin.g-node.org/kcl_cdb/craniofacial_fetal_mri_atlas",
        "license": "CC0 1.0 (public domain dedication)",
        "citation": (
            "Matthew J, Uus A, De Souza L, et al. Craniofacial phenotyping with fetal MRI: a feasibility study of 3D "
            "visualisation, segmentation, surface-rendered and physical models. BMC Med Imaging 24, 52 (2024). "
            "https://doi.org/10.1186/s12880-024-01230-7"
        ),
        "subject": "Atlas built from 12 healthy fetuses (20 to 36 weeks gestational age), 1.5 T MRI",
        "thumbnail": f"{STUDY_ID}/thumbnail.jpg",
        "rawPath": f"raw/volumes/{STUDY_ID}/",
        "rawFiles": len(raw),
        "rawSizeBytes": sum(f.stat().st_size for f in raw),
        "defaultView": "render",
        "defaultPreset": "sepia",
        "defaultCamera": {"azimuth": 145, "elevation": 8},
        "stats": {"landmarks": len(lut["labels"]) - 1, "headVolumeMl": round(head_ml, 1)},
        "layers": [
            {"id": "t2", "label": "T2 MRI", "kind": "mri", "file": f"{STUDY_ID}/t2.nii.gz", "calMin": 0, "calMax": 4200,
             "bytes": (OUT / "t2.nii.gz").stat().st_size},
            {"id": "landmarks", "label": "Facial landmarks", "kind": "labels", "file": f"{STUDY_ID}/landmarks.nii.gz",
             "lut": f"{STUDY_ID}/landmarks.lut.json", "opacity": 1.0, "visible": False,
             "bytes": (OUT / "landmarks.nii.gz").stat().st_size},
        ],
        "dims": list(out_t2.shape[:3]),
        "spacingMm": [round(float(z), 2) for z in zooms],
    }
    (OUT / "study.json").write_text(json.dumps(study, indent=2))
    print(study["dims"], f"head {head_ml:.0f} ml", f"{sum(l['bytes'] for l in study['layers']) / 1e6:.1f} MB", lut["labels"][1:6])


if __name__ == "__main__":
    main()
