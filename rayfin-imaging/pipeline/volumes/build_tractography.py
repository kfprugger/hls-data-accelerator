"""Brain white-matter tractography (HCP1065 population-averaged atlas, Yeh 2022, CC BY-SA 4.0).

87 fibre bundles averaged from 1,065 Human Connectome Project subjects, in ICBM 2009a space. Each bundle
is subsampled and its points thinned so the whole brain loads in a browser, then written as one TRK file
per bundle group so groups can be toggled. Background: ICBM 2009a T1 template (TemplateFlow).

Input : work/tracts/trk/<group>/*.trk.gz, work/tracts/tpl-MNI152NLin2009aAsym_res-1_{T1w,desc-brain_mask}.nii.gz
Output: work/volumes/brain-tractography/{t1.nii.gz, <group>.trk, thumbnail.jpg, study.json}
"""
import json
import pathlib

import nibabel as nib
import numpy as np
from nibabel.streamlines import Tractogram
from nibabel.streamlines.trk import TrkFile
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "work" / "tracts"
OUT = ROOT / "work" / "volumes" / "brain-tractography"
STUDY_ID = "brain-tractography"
MAX_PER_BUNDLE = 400
POINT_STRIDE = 4
GROUPS = [
    ("association", "Association fibres", True),
    ("projection", "Projection fibres", True),
    ("commissural", "Commissural fibres", True),
    ("cerebellum", "Cerebellar fibres", True),
    ("cranial nerve", "Cranial nerves", False),
]


def thin(streamline: np.ndarray) -> np.ndarray:
    idx = list(range(0, len(streamline), POINT_STRIDE))
    if idx[-1] != len(streamline) - 1:
        idx.append(len(streamline) - 1)
    return streamline[idx].astype(np.float32)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)

    t1 = nib.load(SRC / "tpl-MNI152NLin2009aAsym_res-1_T1w.nii.gz")
    mask = np.asanyarray(nib.load(SRC / "tpl-MNI152NLin2009aAsym_res-1_desc-brain_mask.nii.gz").dataobj) > 0
    data = np.asanyarray(t1.dataobj).astype(np.float32) * mask
    data = (data / np.percentile(data[mask], 99.5) * 1000).clip(0, 1200).astype(np.int16)
    t1_out = nib.Nifti1Image(data, t1.affine)
    nib.save(t1_out, OUT / "t1.nii.gz")

    layers = [{"id": "t1", "label": "T1 template (ICBM 2009a)", "file": f"{STUDY_ID}/t1.nii.gz", "kind": "mri",
               "visible": False, "bytes": (OUT / "t1.nii.gz").stat().st_size}]
    all_points, total_lines, bundles, raw_files, raw_bytes = [], 0, 0, 0, 0
    for folder, label, visible in GROUPS:
        lines = []
        for f in sorted((SRC / "trk" / folder).glob("*.trk.gz")):
            raw_files += 1
            raw_bytes += f.stat().st_size
            sl = nib.streamlines.load(f).streamlines
            # Big bundles (e.g. the corpus callosum) keep proportionally more lines so they stay dense.
            n = min(len(sl), max(MAX_PER_BUNDLE, int(len(sl) * 0.02)), 3000)
            pick = rng.choice(len(sl), size=n, replace=False) if len(sl) else []
            lines.extend(thin(sl[i]) for i in sorted(pick))
            bundles += 1
        if not lines:
            continue
        name = folder.replace(" ", "-")
        header = {
            "dimensions": np.array(t1.shape[:3], np.int16),
            "voxel_sizes": np.array(t1.header.get_zooms()[:3], np.float32),
            "voxel_to_rasmm": t1.affine.astype(np.float32),
            "voxel_order": "LAS",
        }
        TrkFile(Tractogram(lines, affine_to_rasmm=np.eye(4)), header=header).save(str(OUT / f"{name}.trk"))
        total_lines += len(lines)
        all_points.extend(lines)
        layers.append({"id": name, "label": label, "file": f"{STUDY_ID}/{name}.trk", "kind": "tracts",
                       "visible": visible, "bytes": (OUT / f"{name}.trk").stat().st_size})
        print(f"{label}: {len(lines)} streamlines, {(OUT / f'{name}.trk').stat().st_size / 1e6:.1f} MB", flush=True)

    # Thumbnail: lateral projection of all streamlines, coloured by direction, on black.
    size = 512
    img = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    pts_all = np.concatenate(all_points)
    lo, hi = pts_all.min(axis=0), pts_all.max(axis=0)
    scale = (size - 40) / max(hi[1] - lo[1], hi[2] - lo[2])
    for s in all_points[::3]:
        d = np.abs(np.diff(s, axis=0))
        d = d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-6)
        for (p0, p1), c in zip(zip(s[:-1], s[1:]), d):
            draw.line([(20 + (p0[1] - lo[1]) * scale, size - 20 - (p0[2] - lo[2]) * scale),
                       (20 + (p1[1] - lo[1]) * scale, size - 20 - (p1[2] - lo[2]) * scale)],
                      fill=tuple(int(40 + 215 * v) for v in c), width=1)
    img.save(OUT / "thumbnail.jpg", quality=90)

    study = {
        "id": STUDY_ID,
        "category": "Neuro",
        "title": "Brain wiring, DTI tractography",
        "subtitle": f"{bundles} white-matter bundles from 1,065 people",
        "modality": "Diffusion MRI tractography (population atlas)",
        "description": (
            "The brain's long-range wiring, reconstructed from diffusion MRI of 1,065 healthy adults in the Human "
            "Connectome Project. Each line is a fibre pathway, coloured by direction: red left to right, green front "
            "to back, blue top to bottom. Toggle the fibre groups, or bring back the T1 brain to see where they run."
        ),
        "source": "HCP1065 Population-Averaged Tractography Atlas (Yeh, 2022), with the ICBM 2009a template via TemplateFlow",
        "sourceUrl": "https://brain.labsolver.org/hcp_trk_atlas.html",
        "license": "CC BY-SA 4.0 (tractography); ICBM 2009a template, McGill free-use licence",
        "citation": (
            "Yeh FC. Population-based tract-to-region connectome of the human brain and its hierarchical topology. "
            "Nat Commun 13, 4933 (2022). https://doi.org/10.1038/s41467-022-32595-4. Data were provided in part by the "
            "Human Connectome Project, WU-Minn Consortium (1U54MH091657)."
        ),
        "subject": "Population atlas, 1,065 healthy young adults",
        "thumbnail": f"{STUDY_ID}/thumbnail.jpg",
        "rawPath": f"raw/volumes/{STUDY_ID}/",
        "rawFiles": raw_files + 2,
        "rawSizeBytes": raw_bytes,
        "defaultView": "render",
        "stats": {"bundles": bundles, "streamlines": total_lines},
        "layers": layers,
        "dims": list(t1.shape[:3]),
        "spacingMm": [round(float(z), 2) for z in t1.header.get_zooms()[:3]],
    }
    (OUT / "study.json").write_text(json.dumps(study, indent=2))
    print(study["subtitle"], total_lines, "streamlines")


if __name__ == "__main__":
    main()
