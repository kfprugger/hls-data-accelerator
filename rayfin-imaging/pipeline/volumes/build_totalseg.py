"""Whole-body CT angiography with 117 labelled structures (TotalSegmentator v2.0.1, CC BY 4.0).

Pulls one subject out of the 23.6 GB Zenodo archive with HTTP range requests (remotezip), merges the
per-structure masks into one label map and writes a colour lookup table grouped by tissue type.

Output: work/volumes/totalseg-ct-angio/{ct.nii.gz, structures.nii.gz, structures.lut.json, thumbnail.jpg, study.json}
"""
import json
import pathlib
import re

import nibabel as nib
import numpy as np
import pandas as pd
from PIL import Image
from remotezip import RemoteZip

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORK = ROOT / "work" / "totalseg"
OUT = ROOT / "work" / "volumes" / "totalseg-ct-angio"
STUDY_ID = "totalseg-ct-angio"
SUBJECT = "s0145"
ZIP_URL = "https://zenodo.org/records/10047292/files/Totalsegmentator_dataset_v201.zip?download=1"

# (pattern, hex colour, alpha) - first match wins. Grouped so the render reads anatomically.
PALETTE = [
    (r"costal_cartilages", "#cfe0e3", 200),
    (r"vertebrae|rib_|sternum|skull|humerus|scapula|clavicula|femur|hip_|sacrum", "#ece2c8", 255),
    (r"atrial_appendage", "#b8324a", 255),
    (r"heart", "#9e1b32", 255),
    (r"pulmonary_vein", "#b0306a", 255),
    (r"portal_vein", "#3f7fd6", 255),
    (r"vein|vena", "#2f63c6", 255),
    (r"aorta|artery|brachiocephalic_trunk", "#d7262b", 255),
    (r"lung_upper_lobe_left", "#f4b6c2", 90), (r"lung_lower_lobe_left", "#eea0b0", 90),
    (r"lung_upper_lobe_right", "#f7c6cf", 90), (r"lung_middle_lobe_right", "#e98ea0", 90),
    (r"lung_lower_lobe_right", "#f2adbb", 90),
    (r"liver", "#8a3322", 255), (r"spleen", "#6b2c5c", 255), (r"kidney_cyst", "#f0d27a", 255),
    (r"kidney", "#c0602d", 255), (r"adrenal", "#f3b33d", 255), (r"gallbladder", "#3f8f3a", 255),
    (r"stomach", "#e08a62", 230), (r"pancreas", "#e8c15a", 255), (r"duodenum", "#d9946a", 230),
    (r"small_bowel", "#e6a77d", 200), (r"colon", "#c97a4d", 200), (r"esophagus", "#c56b6b", 255),
    (r"trachea", "#8fc6d8", 230), (r"thyroid", "#b2457e", 255), (r"urinary_bladder", "#e8d561", 230),
    (r"prostate", "#9a6bb8", 255), (r"brain", "#e7b8b0", 255), (r"spinal_cord", "#f4e08a", 255),
    (r"gluteus|autochthon|iliopsoas", "#b0493c", 110),
]


def colour_for(name: str) -> tuple[int, int, int, int]:
    for pattern, hexcol, alpha in PALETTE:
        if re.search(pattern, name):
            return int(hexcol[1:3], 16), int(hexcol[3:5], 16), int(hexcol[5:7], 16), alpha
    return 200, 200, 200, 200


def pretty(name: str) -> str:
    return name.replace("_", " ").replace("vertebrae ", "vertebra ").capitalize()


def main() -> None:
    sub = WORK / "subject" / SUBJECT
    if not (sub / "ct.nii.gz").exists() or not (WORK / "meta.csv").exists():
        WORK.mkdir(parents=True, exist_ok=True)
        with RemoteZip(ZIP_URL) as z:
            if "meta.csv" in z.namelist() and not (WORK / "meta.csv").exists():
                z.extract("meta.csv", WORK)
            for n in z.namelist():
                if n.startswith(f"{SUBJECT}/") and n.endswith(".nii.gz"):
                    z.extract(n, WORK / "subject")
    meta = pd.read_csv(WORK / "meta.csv", sep=";").set_index("image_id").loc[SUBJECT]

    ct = nib.load(sub / "ct.nii.gz")
    seg_files = sorted((sub / "segmentations").glob("*.nii.gz"))
    names = [f.name.removesuffix(".nii.gz") for f in seg_files]
    labels = np.zeros(ct.shape, np.uint8)
    present = []
    # Paint low-alpha context (muscles, lungs) first so organs and vessels win any overlap.
    order = sorted(range(len(names)), key=lambda i: colour_for(names[i])[3])
    for i in order:
        m = np.asanyarray(nib.load(seg_files[i]).dataobj) > 0
        if m.any():
            labels[m] = i + 1
            present.append(names[i])

    OUT.mkdir(parents=True, exist_ok=True)
    nib.save(nib.Nifti1Image(np.asanyarray(ct.dataobj).astype(np.int16), ct.affine, ct.header), OUT / "ct.nii.gz")
    seg_img = nib.Nifti1Image(labels, ct.affine)
    seg_img.header.set_intent("label")
    nib.save(seg_img, OUT / "structures.nii.gz")

    lut = {"R": [0], "G": [0], "B": [0], "A": [0], "I": [0], "labels": [""]}
    for i, n in enumerate(names):
        r, g, b, a = colour_for(n)
        for k, v in zip("RGBAI", (r, g, b, a, i + 1)):
            lut[k].append(v)
        lut["labels"].append(pretty(n))
    (OUT / "structures.lut.json").write_text(json.dumps(lut))

    # Thumbnail: anterior view of the first labelled structure along each ray, over a bone MIP.
    data = np.asanyarray(ct.dataobj).astype(np.float32)  # (x, y, z) in RAS-ish voxel order
    bone = np.clip((data.max(axis=1) - 150) / 900, 0, 1)  # (x, z)
    seen = labels > 0
    first = np.argmax(seen[:, ::-1, :], axis=1)  # look from anterior (+y) backwards
    xx, zz = np.indices(first.shape)
    hit = seen.any(axis=1)
    lab = labels[xx, labels.shape[1] - 1 - first, zz]
    lut_rgb = np.array([lut["R"], lut["G"], lut["B"]]).T
    rgb = np.where(hit[..., None], lut_rgb[lab], 255 - bone[..., None] * 180)
    rgb = np.transpose(rgb, (1, 0, 2))[::-1, ::-1]  # superior at top, patient right on image left
    zoom = ct.header.get_zooms()
    img = Image.fromarray(rgb.astype(np.uint8)).resize((rgb.shape[1], int(rgb.shape[0] * zoom[2] / zoom[0])))
    img.thumbnail((512, 512))
    canvas = Image.new("RGB", (512, 512), (255, 255, 255))
    canvas.paste(img, ((512 - img.width) // 2, (512 - img.height) // 2))
    canvas.save(OUT / "thumbnail.jpg", quality=90)

    sub_files = list(sub.rglob("*.nii.gz"))
    study = {
        "id": STUDY_ID,
        "category": "Whole body",
        "title": "Whole-body CT angiography, labelled anatomy",
        "subtitle": f"Neck to thighs, {len(present)} labelled structures",
        "modality": "CT angiography",
        "description": (
            "A contrast-enhanced CT from the neck to the thighs with every major organ, vessel, bone and "
            "muscle group segmented. Arteries are red, veins blue, bone ivory, and solid organs in their own "
            "colours. Hide the CT to see the labelled anatomy on its own, or clip through it."
        ),
        "source": "TotalSegmentator dataset v2.0.1 (Wasserthal et al.), University Hospital Basel, via Zenodo",
        "sourceUrl": "https://zenodo.org/records/10047292",
        "license": "CC BY 4.0",
        "citation": (
            "Wasserthal J, Breit HC, Meyer MT, et al. TotalSegmentator: Robust Segmentation of 104 Anatomic "
            "Structures in CT Images. Radiology: Artificial Intelligence, 2023. https://doi.org/10.1148/ryai.230024"
        ),
        "subject": f"{'Male' if meta.gender == 'm' else 'Female'}, {int(meta.age)} years, {meta.manufacturer.title()} {meta.scanner_model.title()}",
        "patientId": SUBJECT,
        "thumbnail": f"{STUDY_ID}/thumbnail.jpg",
        "rawPath": f"raw/volumes/{STUDY_ID}/{SUBJECT}/",
        "rawFiles": len(sub_files),
        "rawSizeBytes": sum(p.stat().st_size for p in sub_files),
        "defaultView": "render",
        "stats": {"structures": len(present)},
        "layers": [
            {"id": "ct", "label": "CT", "file": f"{STUDY_ID}/ct.nii.gz", "kind": "ct",
             "bytes": (OUT / "ct.nii.gz").stat().st_size},
            {"id": "structures", "label": "Anatomy labels", "file": f"{STUDY_ID}/structures.nii.gz", "kind": "labels",
             "lut": f"{STUDY_ID}/structures.lut.json", "opacity": 1.0, "visible": True,
             "bytes": (OUT / "structures.nii.gz").stat().st_size},
        ],
        "dims": list(ct.shape),
        "spacingMm": [round(float(z), 2) for z in zoom],
    }
    (OUT / "study.json").write_text(json.dumps(study, indent=2))
    print(study["subtitle"], study["subject"], study["dims"], [round(l["bytes"] / 1e6, 1) for l in study["layers"]])


if __name__ == "__main__":
    main()
