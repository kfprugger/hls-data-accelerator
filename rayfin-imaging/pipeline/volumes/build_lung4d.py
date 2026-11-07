"""Respiratory-gated 4D CT with per-phase anatomy contours (TCIA 4D-Lung, patient 100, CC BY 3.0).

Ten CT volumes, one per 10% of the breathing cycle, each with RTSTRUCT contours (tumour, lungs,
trachea, heart, oesophagus, cord, vertebra, lymph node). Output is one 4D CT (table removed) and one
4D label map (lungs excluded; the viewer draws them from the CT as glass), so phases switch instantly.

Input : work/lung4d/dicom/{CT_*,RTSTRUCT_*}/*.dcm   (downloaded from NCI Imaging Data Commons)
Output: work/volumes/lung-4dct/{ct4d.nii.gz, anatomy4d.nii.gz, anatomy.lut.json, thumbnail.jpg, study.json}
"""
import glob
import json
import pathlib
import re

import nibabel as nib
import numpy as np
import pydicom
import SimpleITK as sitk
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "lung4d" / "dicom"
OUT = ROOT / "work" / "volumes" / "lung-4dct"
STUDY_ID = "lung-4dct"
SPACING = 2.0

# label id, ROI name prefix, display name, colour, alpha. Painted in this order (later wins).
STRUCTURES = [
    (1, "RLung", "Right lung", "#f2a7b8", 255),
    (2, "LLung", "Left lung", "#f6bccb", 255),
    (3, "Trachea", "Trachea and bronchi", "#7fc3df", 220),
    (4, "Esophagus", "Oesophagus", "#c86b5e", 230),
    (5, "Heart", "Heart", "#a3192e", 200),
    (6, "Vertebra", "Vertebrae", "#ece2c8", 255),
    (7, "Cord", "Spinal cord", "#f4e08a", 255),
    (8, "LN", "Lymph node", "#3cb46e", 255),
    (9, "Tumor", "Tumour (GTV)", "#ff7a1a", 255),
]


def phase_of(desc: str) -> float:
    return float(re.search(r"([\d.]+)%", desc).group(1))


def load_ct(folder: str):
    ds = [pydicom.dcmread(f) for f in glob.glob(folder + "/*.dcm")]
    ds.sort(key=lambda d: float(d.ImagePositionPatient[2]))
    vol = np.stack([d.pixel_array.astype(np.float32) * float(d.RescaleSlope) + float(d.RescaleIntercept) for d in ds])
    ps = [float(v) for v in ds[0].PixelSpacing]
    dz = float(np.median(np.diff([float(d.ImagePositionPatient[2]) for d in ds])))
    img = sitk.GetImageFromArray(vol)
    img.SetSpacing([ps[1], ps[0], dz])
    img.SetOrigin([float(v) for v in ds[0].ImagePositionPatient])
    return img, ds


def rasterise(rt_path: str, ct_ds: list) -> np.ndarray:
    """RTSTRUCT polygons -> label volume on the CT slice grid (z, y, x)."""
    rt = pydicom.dcmread(rt_path)
    names = {r.ROINumber: r.ROIName for r in rt.StructureSetROISequence}
    zs = np.array([float(d.ImagePositionPatient[2]) for d in ct_ds])
    x0, y0 = float(ct_ds[0].ImagePositionPatient[0]), float(ct_ds[0].ImagePositionPatient[1])
    sy, sx = (float(v) for v in ct_ds[0].PixelSpacing)
    rows, cols = ct_ds[0].Rows, ct_ds[0].Columns
    labels = np.zeros((len(ct_ds), rows, cols), np.uint8)
    by_name = {}
    for rc in rt.ROIContourSequence:
        by_name[names.get(rc.ReferencedROINumber, "")] = rc
    for lid, prefix, *_ in STRUCTURES:
        rc = next((v for k, v in by_name.items() if k.lower().startswith(prefix.lower() + "_")), None)
        if rc is None or "ContourSequence" not in rc:
            continue
        per_slice: dict[int, list] = {}
        for c in rc.ContourSequence:
            pts = np.array(c.ContourData, np.float64).reshape(-1, 3)
            k = int(np.argmin(np.abs(zs - pts[0, 2])))
            per_slice.setdefault(k, []).append([((p[0] - x0) / sx, (p[1] - y0) / sy) for p in pts])
        for k, polys in per_slice.items():
            canvas = Image.new("L", (cols, rows), 0)
            draw = ImageDraw.Draw(canvas)
            for poly in polys:
                if len(poly) >= 3:
                    draw.polygon(poly, outline=1, fill=1)
            # XOR-style fill would handle holes; organs here are simple, so union is fine.
            labels[k][np.asarray(canvas) > 0] = lid
    return labels


def body_mask(ct: np.ndarray) -> np.ndarray:
    """Patient outline (z, y, x): largest connected soft-tissue component, holes filled per axial slice."""
    tissue = ndimage.binary_opening(ct > -400, iterations=1)
    lab, n = ndimage.label(tissue)
    if n == 0:
        return tissue
    sizes = ndimage.sum(tissue, lab, range(1, n + 1))
    body = lab == (int(np.argmax(sizes)) + 1)
    body = np.stack([ndimage.binary_fill_holes(z) for z in body])
    return ndimage.binary_dilation(body, iterations=1)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cts = sorted(glob.glob(str(SRC / "CT_*")), key=lambda f: phase_of(pydicom.dcmread(glob.glob(f + "/*.dcm")[0], stop_before_pixels=True).SeriesDescription))
    rts = {}
    for f in glob.glob(str(SRC / "RTSTRUCT_*/*.dcm")):
        rts[phase_of(pydicom.dcmread(f, stop_before_pixels=True).SeriesDescription)] = f

    ref_img = None
    ct_frames, lab_frames, phases, centroids = [], [], [], []
    for folder in cts:
        img, ds = load_ct(folder)
        ph = phase_of(ds[0].SeriesDescription)
        lab = sitk.GetImageFromArray(rasterise(rts[ph], ds))
        lab.CopyInformation(img)
        if ref_img is None:
            size = [int(round(s * sp / SPACING)) for s, sp in zip(img.GetSize(), img.GetSpacing())]
            ref_img = sitk.Image(size, sitk.sitkFloat32)
            ref_img.SetSpacing([SPACING] * 3)
            ref_img.SetOrigin(img.GetOrigin())
            ref_img.SetDirection(img.GetDirection())
        ct2 = sitk.Resample(img, ref_img, sitk.Transform(), sitk.sitkLinear, -1024, sitk.sitkFloat32)
        lb2 = sitk.Resample(lab, ref_img, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
        ct_frames.append(sitk.GetArrayFromImage(ct2))
        la = sitk.GetArrayFromImage(lb2)
        lab_frames.append(la)
        phases.append(ph)
        tum = la == 9
        centroids.append(np.array(ndimage.center_of_mass(tum)) * SPACING if tum.any() else None)
        print(f"phase {ph:4.0f}%  tumour voxels {int(tum.sum())}", flush=True)

    ct4 = np.stack(ct_frames)  # (t, z, y, x)
    lb4 = np.stack(lab_frames)
    body = (ct4.max(axis=0) > -500)
    body = ndimage.binary_opening(body, iterations=2)
    zz, yy, xx = np.nonzero(body)
    sl = [slice(max(0, a.min() - 3), a.max() + 4) for a in (zz, yy, xx)]
    # Keep the chest: the contoured anatomy plus 2 cm above and below (the scan runs well into the abdomen).
    chest = np.isin(lb4.max(axis=0), [1, 2, 3, 5, 9])  # lungs, airway, heart, tumour (vertebrae span the scan)
    lz = np.nonzero(chest.any(axis=(1, 2)))[0]
    sl[0] = slice(max(sl[0].start, lz.min() - 10), min(sl[0].stop, lz.max() + 11))
    sl = tuple(sl)
    ct4 = ct4[(slice(None),) + sl]
    lb4 = lb4[(slice(None),) + sl]
    # Table removal: the couch foam sits in the lung HU range and clutters 3D renders.
    for t in range(ct4.shape[0]):
        ct4[t][~body_mask(ct4[t])] = -1024

    # (t, z, y, x) in LPS -> NIfTI (x, y, z, t) RAS affine.
    origin = np.array(ref_img.GetOrigin()) + np.array([sl[2].start, sl[1].start, sl[0].start]) * SPACING
    affine = np.diag([-SPACING, -SPACING, SPACING, 1.0])
    affine[:3, 3] = [-origin[0], -origin[1], origin[2]]
    ct_nii = nib.Nifti1Image(np.ascontiguousarray(ct4.transpose(3, 2, 1, 0)).astype(np.int16), affine)
    ct_nii.header.set_xyzt_units("mm", "sec")
    nib.save(ct_nii, OUT / "ct4d.nii.gz")
    # Lungs are drawn from the CT itself (glass preset), so drop them from the labels to keep the inside visible.
    is_lung = np.isin(lb4, [1, 2])
    for name, arr in (("anatomy4d", np.where(is_lung, 0, lb4)),):
        lab_nii = nib.Nifti1Image(np.ascontiguousarray(arr.astype(np.uint8).transpose(3, 2, 1, 0)), affine)
        lab_nii.header.set_intent("label")
        nib.save(lab_nii, OUT / f"{name}.nii.gz")

    lut = {"R": [0], "G": [0], "B": [0], "A": [0], "I": [0], "labels": [""]}
    for lid, _, name, hexc, alpha in STRUCTURES:
        for k, v in zip("RGBAI", (int(hexc[1:3], 16), int(hexc[3:5], 16), int(hexc[5:7], 16), alpha, lid)):
            lut[k].append(v)
        lut["labels"].append(name)
    (OUT / "anatomy.lut.json").write_text(json.dumps(lut))

    lung_ml = [float(((f == 1) | (f == 2)).sum() * SPACING**3 / 1000) for f in lb4]
    tidal = max(lung_ml) - min(lung_ml)
    valid = [c for c in centroids if c is not None]
    excursion = float(np.ptp(np.stack(valid), axis=0).max()) if len(valid) > 1 else 0.0
    si_excursion = float(np.ptp(np.stack(valid)[:, 0])) if len(valid) > 1 else 0.0

    # Thumbnail: coronal CT slice through the tumour, contours blended, at end-inhale.
    t0 = 0
    tum = lb4[t0] == 9
    y = int(np.argmax(tum.sum(axis=(0, 2)))) if tum.any() else lb4.shape[2] // 2
    ct_sl = np.clip((ct4[t0, :, y, :] + 1000) / 1400, 0, 1)[::-1, ::-1] * 255
    lb_sl = lb4[t0, :, y, :][::-1, ::-1]
    col = np.zeros((10, 3))
    for lid, _, _, hexc, alpha in STRUCTURES:
        col[lid] = [int(hexc[i:i + 2], 16) for i in (1, 3, 5)]
    rgb = np.repeat(ct_sl[..., None], 3, axis=2)
    mask = lb_sl > 0
    rgb[mask] = 0.45 * rgb[mask] + 0.55 * col[lb_sl[mask]]
    pil = Image.fromarray(rgb.astype(np.uint8))
    pil.thumbnail((512, 512))
    canvas = Image.new("RGB", (512, 512), (255, 255, 255))
    canvas.paste(pil, ((512 - pil.width) // 2, (512 - pil.height) // 2))
    canvas.save(OUT / "thumbnail.jpg", quality=90)

    raw = [pathlib.Path(p) for p in glob.glob(str(SRC / "*/*.dcm"))]
    d0 = pydicom.dcmread(glob.glob(cts[0] + "/*.dcm")[0], stop_before_pixels=True)
    frames = [
        {"value": int(p), "label": f"{int(p)}%", "frameIndex": i, "layers": {}, "bytes": 0,
         "note": f"lungs {lung_ml[i]:,.0f} ml"}
        for i, p in enumerate(phases)
    ]
    study = {
        "id": STUDY_ID,
        "category": "Thoracic",
        "title": "Breathing lungs, 4D CT",
        "subtitle": f"Ten respiratory phases, lungs change by {tidal:,.0f} ml",
        "modality": "Respiratory-gated 4D CT with RT structures",
        "description": (
            "A radiotherapy planning CT recorded across the breathing cycle, one volume for every 10% of a "
            f"breath. The lungs are rendered as glass straight from the CT, inflating and emptying by about "
            f"{tidal:,.0f} ml, with the tumour (orange), airway, heart and spine moving inside them. Tracking this "
            "motion is how radiotherapy teams set treatment margins."
        ),
        "source": "The Cancer Imaging Archive, 4D-Lung (Hugo et al.), via NCI Imaging Data Commons",
        "sourceUrl": "https://www.cancerimagingarchive.net/collection/4d-lung/",
        "license": "CC BY 3.0",
        "citation": (
            "Hugo GD, Weiss E, Sleeman WC, et al. Data from 4D Lung Imaging of NSCLC Patients. The Cancer Imaging "
            "Archive, 2016. https://doi.org/10.7937/K9/TCIA.2016.ELN8YGLE"
        ),
        "subject": f"{'Male' if getattr(d0, 'PatientSex', '') == 'M' else 'Patient'} with non-small cell lung cancer",
        "patientId": str(d0.PatientID),
        "scanner": f"{getattr(d0, 'Manufacturer', '')} CT, 4D gated".strip(),
        "thumbnail": f"{STUDY_ID}/thumbnail.jpg",
        "rawPath": f"raw/volumes/{STUDY_ID}/dicom/",
        "rawFiles": len(raw),
        "rawSizeBytes": sum(p.stat().st_size for p in raw),
        "defaultView": "render",
        "defaultPreset": "lungs",
        "stats": {"phases": len(phases), "lungVolumeChangeMl": round(tidal), "tumourMotionMm": round(excursion, 1)},
        "layers": [
            {"id": "ct", "label": "CT (lungs rendered as glass in 3D)", "file": f"{STUDY_ID}/ct4d.nii.gz", "kind": "ct",
             "frames4d": True, "visible": True, "bytes": (OUT / "ct4d.nii.gz").stat().st_size},
            {"id": "anatomy", "label": "Tumour, airway, heart, spine", "file": f"{STUDY_ID}/anatomy4d.nii.gz",
             "kind": "labels", "frames4d": True, "lut": f"{STUDY_ID}/anatomy.lut.json", "opacity": 1.0, "visible": True,
             "bytes": (OUT / "anatomy4d.nii.gz").stat().st_size},
        ],
        "timeline": {"label": "Breathing phase", "unit": "% of cycle", "initial": 0, "mode": "frames4d", "fps": 3, "loop": True,
                     "frames": frames},
        "dims": list(ct_nii.shape[:3]),
        "spacingMm": [SPACING] * 3,
    }
    (OUT / "study.json").write_text(json.dumps(study, indent=2))
    print(study["subtitle"], study["dims"], [round(l["bytes"] / 1e6, 1) for l in study["layers"]])


if __name__ == "__main__":
    main()
