"""Convert multi-slice DICOM series from the deployed HLS cohort into NIfTI volumes for NiiVue.

Reads `_manifest/studies/*/*.json` from the deployment's `dicom-output` ADLS Gen2 container,
selects multi-slice 3D series (CT/MR/PT with >= 25 slices), downloads their `.dcm` slices,
reconstructs 3D NIfTI volumes and coronal MIP thumbnails, and writes `work/volumes/cohort-*/study.json`.
"""
import argparse
import glob
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import fabric_config  # noqa: E402
import numpy as np
import pydicom
import SimpleITK as sitk
from PIL import Image
ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT_ROOT = ROOT / "work" / "volumes"


def _geometry(datasets: list):
    valid = [d for d in datasets if hasattr(d, "ImagePositionPatient") and hasattr(d, "ImageOrientationPatient")]
    if len(valid) < 16:
        raise ValueError(f"Insufficient oriented slices ({len(valid)})")
    iop = [float(v) for v in valid[0].ImageOrientationPatient]
    row, col = np.array(iop[:3]), np.array(iop[3:])
    normal = np.cross(row, col)
    by_z = {}
    for d in valid:
        z = round(float(np.dot(normal, [float(v) for v in d.ImagePositionPatient])), 3)
        by_z[z] = d
    ordered = [by_z[z] for z in sorted(by_z)]
    if len(ordered) < 16:
        raise ValueError(f"Insufficient unique slice positions ({len(ordered)})")
    pos = [np.array([float(v) for v in d.ImagePositionPatient]) for d in ordered]
    dz = float(np.median(np.diff([np.dot(normal, p) for p in pos])))
    if dz <= 0:
        dz = float(getattr(ordered[0], "SliceThickness", 2.0) or 2.0)
    ps = [float(v) for v in getattr(ordered[0], "PixelSpacing", [1.0, 1.0])]
    direction = [float(x) for x in [row[0], col[0], normal[0], row[1], col[1], normal[1], row[2], col[2], normal[2]]]
    return [float(x) for x in pos[0]], [float(ps[1]), float(ps[0]), float(dz)], direction, ordered


def build_cohort_study(rec: dict, dcm_dir: pathlib.Path, storage_account: str, container: str) -> dict | None:
    files = sorted(glob.glob(str(dcm_dir / "*.dcm")))
    if len(files) < 16:
        return None
    ds = [pydicom.dcmread(f) for f in files]
    origin, spacing, direction, ds = _geometry(ds)
    vol = np.stack([
        d.pixel_array.astype(np.float32) * float(getattr(d, "RescaleSlope", 1.0)) + float(getattr(d, "RescaleIntercept", 0.0))
        for d in ds
    ])
    img = sitk.GetImageFromArray(vol)
    img.SetOrigin(origin)
    img.SetSpacing(spacing)
    img.SetDirection(direction)

    # Resample to 2.0 mm isotropic so browser streaming is fast (~5-12 MB per cohort study)
    target_sp = 2.0
    size = [max(16, int(round(sz * sp / target_sp))) for sz, sp in zip(img.GetSize(), img.GetSpacing())]
    img2 = sitk.Resample(
        img, size, sitk.Transform(), sitk.sitkLinear,
        img.GetOrigin(), [target_sp] * 3, img.GetDirection(), -1024, sitk.sitkInt16,
    )

    patient_id = str(rec.get("patientId") or "unknown")
    short_id = patient_id.split("-")[0]
    study_id = f"cohort-{short_id}"
    out_dir = OUT_ROOT / study_id
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    modality = str(rec.get("actualModality") or rec.get("plannedModality") or "CT").upper()
    layer_kind = "mri" if modality == "MR" else "ct"
    fname = "mri.nii.gz" if layer_kind == "mri" else "ct.nii.gz"
    out_path = out_dir / fname
    sitk.WriteImage(img2, str(out_path), useCompression=True)

    # Generate 512x512 coronal MIP thumbnail
    arr = sitk.GetArrayFromImage(img2).astype(np.float32)  # (z, y, x)
    mip = arr.max(axis=1)[::-1]
    lo, hi = np.percentile(mip, [10, 99.5])
    norm = np.clip((mip - lo) / max(hi - lo, 1.0), 0, 1)
    pil = Image.fromarray((norm * 255).astype(np.uint8)).convert("RGB")
    pil.thumbnail((480, 480), Image.LANCZOS)
    canvas = Image.new("RGB", (512, 512), (18, 18, 18))
    canvas.paste(pil, ((512 - pil.width) // 2, (512 - pil.height) // 2))
    canvas.save(out_dir / "thumbnail.jpg", "JPEG", quality=90)

    cond = rec.get("conditionDisplay") or "Clinical cohort imaging"
    body_part = rec.get("bodySiteDisplay") or rec.get("bodyPartExamined") or "Chest"
    device_id = rec.get("deviceId") or "Masimo Radius-7"
    collection = rec.get("sourceCollection") or "TCIA"

    study = {
        "id": study_id,
        "category": "HLS Cohort Patients",
        "title": f"Patient {short_id} — {body_part} {modality}",
        "subtitle": f"{cond} · {device_id} ({len(ds)} slices)",
        "modality": f"{modality} ({body_part})",
        "description": (
            f"3D {modality} volume reconstructed directly from the deployed HLS synthetic patient cohort "
            f"(Patient {patient_id}, monitored on {device_id} with {cond}). Re-tagged from {collection} "
            f"in ADLS Gen2 ({storage_account}/{container}) and converted into a browser-ready NIfTI volume."
        ),
        "source": f"HLS Data Accelerator Cohort ({collection} via ADLS Gen2 {storage_account})",
        "sourceUrl": "https://www.cancerimagingarchive.net/",
        "license": "CC BY 4.0 / TCIA Open Access",
        "citation": f"HLS Data Accelerator synthetic patient {patient_id} ({collection}, study {rec.get('studyInstanceUid', '')}).",
        "subject": f"Patient {patient_id} ({device_id}) · {cond}",
        "patientId": patient_id,
        "thumbnail": f"{study_id}/thumbnail.jpg",
        "rawPath": f"{rec.get('blobBasePath', '')}/",
        "rawFiles": len(ds),
        "rawSizeBytes": sum(os.path.getsize(f) for f in files),
        "defaultView": "render",
        "defaultPreset": "lungs" if layer_kind == "ct" and "chest" in body_part.lower() else ("bone" if layer_kind == "ct" else None),
        "layers": [
            {
                "id": layer_kind,
                "label": f"{modality} volume",
                "file": f"{study_id}/{fname}",
                "kind": layer_kind,
                "bytes": out_path.stat().st_size,
            }
        ],
        "dims": [int(x) for x in img2.GetSize()[:3]],
        "spacingMm": [round(float(z), 2) for z in img2.GetSpacing()[:3]],
    }
    (out_dir / "study.json").write_text(json.dumps(study, indent=2))
    print(f"Built cohort 3D volume {study_id}: {study['dims']} ({out_path.stat().st_size / 1e6:.1f} MB)")
    return study


def _load_onelake_process_zips() -> tuple[str | None, str | None, list[str]]:
    try:
        ws_id = fabric_config.get("WORKSPACE_ID")
        fab_tok = subprocess.check_output([
            "az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com", "--query", "accessToken", "-o", "tsv",
        ]).decode().strip()
        req = urllib.request.Request(
            f"https://api.fabric.microsoft.com/v1/workspaces/{ws_id}/lakehouses",
            headers={"Authorization": f"Bearer {fab_tok}", "x-ms-fabric-skill": "onelake-dfs-file-inspection"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            lhs = json.loads(resp.read().decode()).get("value", [])
        bronze = next((l for l in lhs if "bronze" in l.get("displayName", "").lower()), None)
        if not bronze:
            return ws_id, None, []
        st_tok = subprocess.check_output([
            "az", "account", "get-access-token", "--resource", "https://storage.azure.com", "--query", "accessToken", "-o", "tsv",
        ]).decode().strip()
        u = f"https://onelake.dfs.fabric.microsoft.com/{ws_id}?resource=filesystem&directory={bronze['id']}/Files/Process/Imaging/DICOM&recursive=true"
        r = urllib.request.Request(u, headers={"Authorization": f"Bearer {st_tok}", "x-ms-version": "2023-11-03", "x-ms-fabric-skill": "onelake-dfs-file-inspection"})
        with urllib.request.urlopen(r, timeout=30) as resp:
            paths = [p["name"] for p in json.loads(resp.read().decode()).get("paths", []) if not p.get("isDirectory") and p.get("name", "").endswith(".dcm.zip")]
        return ws_id, st_tok, paths
    except Exception:
        return None, None, []


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--storage-account", required=True, help="ADLS Gen2 storage account holding dicom-output")
    ap.add_argument("--container", default="dicom-output", help="DICOM blob container name")
    ap.add_argument("--limit", type=int, default=3, help="Maximum cohort 3D studies to build")
    args = ap.parse_args()

    out = subprocess.check_output([
        "az", "storage", "blob", "list",
        "--account-name", args.storage_account,
        "--container-name", args.container,
        "--prefix", "_manifest/studies/",
        "--auth-mode", "login", "-o", "json",
    ])
    blobs = [
        b for b in json.loads(out.decode())
        if b["name"].endswith(".json") and (b.get("properties", {}).get("contentLength") or 0) > 2000
    ]
    ws_id, st_tok, onelake_zips = None, None, []
    built = 0
    for b in blobs:
        if built >= args.limit:
            break
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            manifest_file = tmp_path / "manifest.json"
            subprocess.check_call([
                "az", "storage", "blob", "download",
                "--account-name", args.storage_account,
                "--container-name", args.container,
                "--name", b["name"],
                "--file", str(manifest_file),
                "--auth-mode", "login", "--only-show-errors",
            ], stdout=subprocess.DEVNULL)
            rec = json.loads(manifest_file.read_text())
            if int(rec.get("instanceCount") or 0) < 25 or str(rec.get("actualModality") or "") not in {"CT", "MR", "PT"}:
                continue
            blob_base = rec.get("blobBasePath", "").strip("/")
            if not blob_base:
                continue
            dcm_dir = tmp_path / "dcm"
            dcm_dir.mkdir()
            subprocess.check_call([
                "az", "storage", "blob", "download-batch",
                "--account-name", args.storage_account,
                "--source", args.container,
                "--pattern", f"{blob_base}/*.dcm",
                "--destination", str(dcm_dir),
                "--auth-mode", "login", "--only-show-errors",
            ], stdout=subprocess.DEVNULL)
            flat_dir = tmp_path / "flat"
            flat_dir.mkdir()
            for idx, p in enumerate(dcm_dir.rglob("*.dcm")):
                shutil.move(str(p), str(flat_dir / f"{idx:04d}.dcm"))
            if len(list(flat_dir.glob("*.dcm"))) < 16:
                if ws_id is None and not onelake_zips:
                    ws_id, st_tok, onelake_zips = _load_onelake_process_zips()
                matching = [zp for zp in onelake_zips if f"/{blob_base}/" in zp]
                for idx, zp in enumerate(matching):
                    u = f"https://onelake.dfs.fabric.microsoft.com/{ws_id}/{zp}"
                    r = urllib.request.Request(u, headers={"Authorization": f"Bearer {st_tok}", "x-ms-version": "2023-11-03", "x-ms-fabric-skill": "onelake-dfs-file-inspection"})
                    with urllib.request.urlopen(r, timeout=30) as resp:
                        zbytes = resp.read()
                    with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
                        for name in zf.namelist():
                            if not name.endswith("/"):
                                (flat_dir / f"{idx:04d}.dcm").write_bytes(zf.read(name))
                                break
            try:
                if build_cohort_study(rec, flat_dir, args.storage_account, args.container):
                    built += 1
            except Exception as exc:
                print(f"Skipping {b['name']}: {exc}")
    print(f"Cohort DICOM-to-NIfTI bridge complete: {built} studies built")


if __name__ == "__main__":
    main()
