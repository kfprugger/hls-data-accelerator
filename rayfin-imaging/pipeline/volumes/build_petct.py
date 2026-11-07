"""Whole-body FDG PET/CT (TCIA FDG-PET-CT-Lesions, CC BY 4.0) -> NIfTI layers for NiiVue.

Input : work/petct/study/{CT,PT,SEG}/*.dcm   (downloaded from NCI Imaging Data Commons with idc-index)
Output: work/volumes/petct-whole-body/{ct.nii.gz, pet_suv.nii.gz, lesions.nii.gz, lesions.lut.json,
                                        thumbnail.jpg, study.json}

PET voxels are converted to body-weight SUV (decay-corrected to series start). Expert lesion masks
come from the collection's DICOM SEG objects.
"""
import datetime as dt
import glob
import json
import math
import pathlib

import numpy as np
import pydicom
import SimpleITK as sitk
from PIL import Image
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "petct" / "study"
OUT = ROOT / "work" / "volumes" / "petct-whole-body"
STUDY_ID = "petct-whole-body"


def _geometry(datasets: list) -> tuple[list[float], list[float], list[float], list]:
    iop = [float(v) for v in datasets[0].ImageOrientationPatient]
    row, col = np.array(iop[:3]), np.array(iop[3:])
    normal = np.cross(row, col)
    datasets.sort(key=lambda d: float(np.dot(normal, [float(v) for v in d.ImagePositionPatient])))
    pos = [np.array([float(v) for v in d.ImagePositionPatient]) for d in datasets]
    dz = float(np.median(np.diff([np.dot(normal, p) for p in pos])))
    ps = [float(v) for v in datasets[0].PixelSpacing]
    direction = [row[0], col[0], normal[0], row[1], col[1], normal[1], row[2], col[2], normal[2]]
    return list(pos[0]), [ps[1], ps[0], dz], direction, datasets


def read_series(folder: pathlib.Path, scale_fn=None) -> tuple[sitk.Image, list]:
    ds = [pydicom.dcmread(f) for f in glob.glob(str(folder / "*.dcm"))]
    origin, spacing, direction, ds = _geometry(ds)
    vol = np.stack([
        d.pixel_array.astype(np.float32) * float(getattr(d, "RescaleSlope", 1)) + float(getattr(d, "RescaleIntercept", 0))
        for d in ds
    ])
    if scale_fn:
        vol *= scale_fn(ds[0])
    img = sitk.GetImageFromArray(vol)
    img.SetOrigin(origin)
    img.SetSpacing(spacing)
    img.SetDirection(direction)
    return img, ds


def suv_factor(d) -> float:
    """Bq/ml -> SUVbw, decay-corrected to series start (DecayCorrection = START)."""
    rp = d.RadiopharmaceuticalInformationSequence[0]
    dose = float(rp.RadionuclideTotalDose)
    half_life = float(rp.RadionuclideHalfLife)
    t = lambda s: dt.datetime.strptime(str(s).split(".")[0].rjust(6, "0"), "%H%M%S")
    elapsed = (t(d.SeriesTime) - t(rp.RadiopharmaceuticalStartTime)).total_seconds()
    decayed = dose * math.exp(-math.log(2) * elapsed / half_life)
    return float(d.PatientWeight) * 1000.0 / decayed


def read_seg(path: str) -> sitk.Image:
    d = pydicom.dcmread(path)
    frames = d.pixel_array.astype(np.uint8)
    if frames.ndim == 2:
        frames = frames[None]
    fg = d.PerFrameFunctionalGroupsSequence
    iop = [float(v) for v in d.SharedFunctionalGroupsSequence[0].PlaneOrientationSequence[0].ImageOrientationPatient]
    row, col = np.array(iop[:3]), np.array(iop[3:])
    normal = np.cross(row, col)
    pos = np.array([[float(v) for v in f.PlanePositionSequence[0].ImagePositionPatient] for f in fg])
    order = np.argsort(pos @ normal)
    pm = d.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0]
    ps = [float(v) for v in pm.PixelSpacing]
    dz = float(np.median(np.diff((pos @ normal)[order])))
    img = sitk.GetImageFromArray(frames[order])
    img.SetOrigin(list(pos[order[0]]))
    img.SetSpacing([ps[1], ps[0], dz])
    img.SetDirection([row[0], col[0], normal[0], row[1], col[1], normal[1], row[2], col[2], normal[2]])
    return img


def crop_to(img: sitk.Image, mask: np.ndarray, margin: int = 4) -> sitk.Image:
    zz, yy, xx = np.nonzero(mask)
    lo = [max(0, int(a.min()) - margin) for a in (xx, yy, zz)]
    hi = [min(s, int(a.max()) + 1 + margin) for a, s in zip((xx, yy, zz), img.GetSize())]
    return sitk.RegionOfInterest(img, [h - l for l, h in zip(lo, hi)], lo)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ct, ct_ds = read_series(SRC / "CT")
    pet, pet_ds = read_series(SRC / "PT", scale_fn=suv_factor)
    seg = read_seg(glob.glob(str(SRC / "SEG" / "*.dcm"))[0])

    # CT: 2 mm isotropic, cropped to the body (HU > -500), int16 HU.
    spacing = 2.0
    size = [int(round(sz * sp / spacing)) for sz, sp in zip(ct.GetSize(), ct.GetSpacing())]
    ct2 = sitk.Resample(ct, size, sitk.Transform(), sitk.sitkLinear, ct.GetOrigin(), [spacing] * 3, ct.GetDirection(), -1024, sitk.sitkFloat32)
    body = ndimage.binary_opening(sitk.GetArrayFromImage(ct2) > -500, iterations=2)
    lab, k = ndimage.label(body)
    body = lab == (1 + int(np.argmax(ndimage.sum(body, lab, range(1, k + 1)))))
    ct2 = sitk.Cast(crop_to(ct2, body), sitk.sitkInt16)
    sitk.WriteImage(ct2, str(OUT / "ct.nii.gz"), useCompression=True)

    # PET: native grid, cropped to where there is signal, uint16 with 0.001 SUV steps.
    suv = sitk.GetArrayFromImage(pet)
    pet_c = crop_to(pet, suv > 0.3)
    arr = sitk.GetArrayFromImage(pet_c).clip(0, 65.5)
    pet_u16 = sitk.GetImageFromArray(np.round(arr * 1000).astype(np.uint16))
    pet_u16.CopyInformation(pet_c)
    sitk.WriteImage(pet_u16, str(OUT / "pet_suv_raw.nii.gz"), useCompression=True)
    # Store SUV as uint16 with a header scale factor; nibabel derives scl_slope when saving float data
    # into an integer dtype (setting scl_slope by hand is discarded on save).
    import nibabel as nib
    im = nib.load(OUT / "pet_suv_raw.nii.gz")
    suv_f = np.asanyarray(im.dataobj).astype(np.float32) / 1000.0
    out = nib.Nifti1Image(suv_f, im.affine)
    out.set_data_dtype(np.uint16)
    nib.save(out, OUT / "pet_suv.nii.gz")
    (OUT / "pet_suv_raw.nii.gz").unlink()

    # Lesions: resample SEG onto the cropped PET grid, label = 1.
    seg_r = sitk.Resample(seg, pet_c, sitk.Transform(), sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
    les = sitk.GetArrayFromImage(seg_r) > 0
    n_lesions = int(ndimage.label(les)[1])
    seg_r = sitk.GetImageFromArray(les.astype(np.uint8))
    seg_r.CopyInformation(pet_c)
    sitk.WriteImage(seg_r, str(OUT / "lesions.nii.gz"), useCompression=True)
    lesion_ml = float(les.sum() * np.prod(pet_c.GetSpacing()) / 1000)
    (OUT / "lesions.lut.json").write_text(json.dumps({
        "R": [0, 40], "G": [0, 220], "B": [0, 200], "A": [0, 255], "I": [0, 1], "labels": ["", "Lesion"],
    }))

    # Thumbnail: classic inverted coronal PET MIP.
    mip = arr.max(axis=1)  # (z, x) - SimpleITK arrays are (z, y, x) in LPS; y runs anterior->posterior
    img = (255 - np.clip(mip / 8.0, 0, 1) * 255).astype(np.uint8)[::-1]  # superior at top
    pil = Image.fromarray(img).resize((img.shape[1], int(img.shape[0] * pet_c.GetSpacing()[2] / pet_c.GetSpacing()[0])))
    pil.thumbnail((512, 512))
    canvas = Image.new("L", (512, 512), 255)
    canvas.paste(pil, ((512 - pil.width) // 2, (512 - pil.height) // 2))
    canvas.convert("RGB").save(OUT / "thumbnail.jpg", quality=90)

    d0 = pet_ds[0]
    raw_bytes = sum(p.stat().st_size for p in SRC.rglob("*.dcm"))
    n_files = len(list(SRC.rglob("*.dcm")))
    study = {
        "id": STUDY_ID,
        "category": "Whole body",
        "title": "Whole-body FDG PET/CT",
        "subtitle": f"Oncology staging, {n_lesions} FDG-avid lesions",
        "modality": "PET/CT",
        "description": (
            "An 18F-FDG PET/CT from skull base to thighs. The CT shows anatomy; the PET overlay, in SUV, shows "
            "where glucose is being consumed. Tumour deposits glow against normal uptake in the brain, heart, "
            "kidneys and bladder. Expert lesion masks from the collection can be shown on top."
        ),
        "source": "The Cancer Imaging Archive, FDG-PET-CT-Lesions (Gatidis et al.), via NCI Imaging Data Commons",
        "sourceUrl": "https://www.cancerimagingarchive.net/collection/fdg-pet-ct-lesions/",
        "license": "CC BY 4.0",
        "citation": (
            "Gatidis S, Kuestner T. A whole-body FDG-PET/CT dataset with manually annotated tumor lesions "
            "(FDG-PET-CT-Lesions). The Cancer Imaging Archive, 2022. https://doi.org/10.7937/gkr0-xv29"
        ),
        "subject": f"{'Male' if d0.PatientSex == 'M' else 'Female'}, {int(str(d0.PatientAge)[:3])} years, {d0.PatientWeight} kg",
        "patientId": d0.PatientID,
        "scanner": f"{d0.Manufacturer} {d0.ManufacturerModelName}",
        "thumbnail": f"{STUDY_ID}/thumbnail.jpg",
        "rawPath": f"raw/volumes/{STUDY_ID}/dicom/",
        "rawFiles": n_files,
        "rawSizeBytes": raw_bytes,
        "defaultView": "render",
        "stats": {"lesions": n_lesions, "lesionVolumeMl": round(lesion_ml, 1),
                  "suvMax": round(float(arr.max()), 1), "injectedMBq": round(float(d0.RadiopharmaceuticalInformationSequence[0].RadionuclideTotalDose) / 1e6)},
        "layers": [
            {"id": "ct", "label": "CT", "file": f"{STUDY_ID}/ct.nii.gz", "kind": "ct",
             "bytes": (OUT / "ct.nii.gz").stat().st_size, "dims": list(ct2.GetSize()), "spacingMm": [round(s, 2) for s in ct2.GetSpacing()]},
            {"id": "pet", "label": "PET (SUV)", "file": f"{STUDY_ID}/pet_suv.nii.gz", "kind": "overlay",
             "colormap": "hot", "calMin": 2.5, "calMax": 10, "opacity": 0.85, "visible": True, "unit": "SUV",
             "bytes": (OUT / "pet_suv.nii.gz").stat().st_size, "dims": list(pet_c.GetSize()), "spacingMm": [round(s, 2) for s in pet_c.GetSpacing()]},
            {"id": "lesions", "label": "Expert lesion masks", "file": f"{STUDY_ID}/lesions.nii.gz", "kind": "labels",
             "lut": f"{STUDY_ID}/lesions.lut.json", "opacity": 0.9, "visible": False,
             "bytes": (OUT / "lesions.nii.gz").stat().st_size},
        ],
        "dims": list(ct2.GetSize()),
        "spacingMm": [round(s, 2) for s in ct2.GetSpacing()],
    }
    (OUT / "study.json").write_text(json.dumps(study, indent=2))
    print(json.dumps({k: study[k] for k in ("subtitle", "subject", "stats", "dims")}, indent=1))
    for l in study["layers"]:
        print(l["id"], round(l["bytes"] / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
