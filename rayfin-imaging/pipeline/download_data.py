"""Download the public source datasets for the 3D/4D studies and the multiplex slide into work/.

    python pipeline/download_data.py all                 # everything below (about 25 GB)
    python pipeline/download_data.py petct lung4d fetal  # or pick datasets

Nothing here is redistributed by this repository: every file comes straight from its original
publisher, under that publisher's licence (see README, "Data sources"). The TCGA H&E slides have
their own script (pipeline/download_slides.py) and TotalSegmentator is fetched by its builder.

Datasets (name: source -> folder, approximate size):
  petct      NCI Imaging Data Commons, TCIA FDG-PET-CT-Lesions (CC BY 4.0)      -> work/petct/study       0.3 GB
  lung4d     NCI Imaging Data Commons, TCIA 4D-Lung (CC BY 3.0)                 -> work/lung4d/dicom      0.8 GB
  multiplex  NCI Imaging Data Commons, HTAN HMS CyCIF (CC BY 4.0), 8 markers    -> work/mif               2.9 GB
  vhp        U.S. NLM Visible Human Female, cryosection PNGs (public domain)    -> work/vhp/png          16.5 GB
  tracts     HCP1065 tractography atlas (CC BY-SA 4.0) + TemplateFlow template  -> work/tracts            0.6 GB
  fetal      King's College London fetal MRI atlases on G-Node GIN (CC0):
               fetal-brain (dHCP), fetal-body (0.55T body atlas), fetal-face    -> work/fetal_*           0.4 GB
Downloads resume: files that already exist with a non-zero size are skipped.
"""
import argparse
import concurrent.futures as cf
import json
import pathlib
import shutil
import sys
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
SOURCES = pathlib.Path(__file__).resolve().parent / "sources"

# TCIA FDG-PET-CT-Lesions, patient PETCT_5e2da717db (62-year-old male): CT, PET and the expert lesion SEG.
PETCT_SERIES = {
    "CT": "1.3.6.1.4.1.14519.5.2.1.337453420498619047725801274799122979476",
    "PT": "1.3.6.1.4.1.14519.5.2.1.66013956297229174034130282939084505274",
    "SEG": "1.3.6.1.4.1.14519.5.2.1.315358702450484779130076575633701401023",
}

# TCIA 4D-Lung, patient 100_HM10395, 2003-07-02 planning 4D CT: ten respiratory phases (CT) and their RTSTRUCTs.
LUNG4D_SERIES = [
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.660205801121995704108596829193",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.124579141450014659493072582400",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.238102828057750190064634581534",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.104367227242206784402589566113",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.346792788302694778312512645229",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.235823857759482707932854857212",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.211370457211109403388277199194",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.309178825287344133434085485451",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.103521604337852189272990015277",
    "1.3.6.1.4.1.14519.5.2.1.6834.5010.334245065657098504984831070956",
] + [f"2.25.5618076857306634880164728989441809423.{i}" for i in range(1, 11)]

# HTAN HMS CyCIF slide HTA7_920_1000: the 1.3 um/pixel (12,460 px wide) pyramid level of the 8 markers shown.
MULTIPLEX_SOP = {
    "DNA": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.17.0",
    "Pan-cytokeratin": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.437.0",
    "Aortic smooth muscle actin": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.479.0",
    "CD45": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.605.0",
    "CD8a": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.815.0",
    "CD68": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.773.0",
    "Antigen Ki67": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.395.0",
    "CD31": "1.3.6.1.4.1.5962.99.1.2343322182.1764456793.1655905763910.1319.0",
}

VHP_BASE = "https://data.lhncbc.nlm.nih.gov/public/Visible-Human/Female-Images/PNG_format"
HCP1065_ZIP = "https://github.com/frankyeh/data-atlas/releases/download/hcp1065/hcp1065_avg_tracts_trk.zip"
TEMPLATEFLOW = "https://templateflow.s3.amazonaws.com/tpl-MNI152NLin2009aAsym"
GIN = "https://gin.g-node.org/kcl_cdb"


def fetch(url: str, dest: pathlib.Path) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    import time
    for attempt in range(1, 6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "rayfin-imaging-pipeline"})
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.rename(dest)
            return
        except Exception:
            if attempt == 5:
                raise
            time.sleep(5 * attempt)

def fetch_many(jobs: list[tuple[str, pathlib.Path]], label: str, workers: int = 8) -> None:
    todo = [(u, d) for u, d in jobs if not (d.exists() and d.stat().st_size > 0)]
    print(f"{label}: {len(jobs) - len(todo)} of {len(jobs)} files present, downloading {len(todo)}", flush=True)
    with cf.ThreadPoolExecutor(workers) as ex:
        futures = {ex.submit(fetch, u, d): u for u, d in todo}
        for i, fut in enumerate(cf.as_completed(futures), 1):
            fut.result()
            if i % 200 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)


def idc():
    from idc_index import IDCClient

    return IDCClient()


def petct() -> None:
    out = WORK / "petct" / "study"
    client = idc()
    for modality, uid in PETCT_SERIES.items():
        if any((out / modality).glob("*.dcm")):
            continue
        print(f"petct: {modality} series from IDC", flush=True)
        client.download_from_selection(downloadDir=str(out), seriesInstanceUID=[uid], dirTemplate="%Modality")


def lung4d() -> None:
    out = WORK / "lung4d" / "dicom"
    print(f"lung4d: {len(LUNG4D_SERIES)} series from IDC", flush=True)
    idc().download_from_selection(downloadDir=str(out), seriesInstanceUID=LUNG4D_SERIES,
                                  dirTemplate="%Modality_%SeriesInstanceUID")


def multiplex() -> None:
    import pydicom

    out = WORK / "mif" / "level4"
    out.mkdir(parents=True, exist_ok=True)
    client = idc()
    client.fetch_index("sm_instance_index")
    print(f"multiplex: {len(MULTIPLEX_SOP)} marker images from IDC (about 360 MB each)", flush=True)
    client.download_from_selection(downloadDir=str(out), sopInstanceUID=list(MULTIPLEX_SOP.values()), dirTemplate=None)
    by_uid = {}
    for f in out.rglob("*.dcm"):
        by_uid[pydicom.dcmread(f, stop_before_pixels=True).SOPInstanceUID] = f.relative_to(out.parent).as_posix()
    missing = [n for n, uid in MULTIPLEX_SOP.items() if uid not in by_uid]
    if missing:
        raise SystemExit(f"multiplex: not downloaded: {missing}")
    (WORK / "mif" / "level4_channels.json").write_text(
        json.dumps({n: by_uid[uid] for n, uid in MULTIPLEX_SOP.items()}, indent=1))


def vhp() -> None:
    jobs = []
    for line in (SOURCES / "visible_human_female.txt").read_text().splitlines():
        if line and not line.startswith("#"):
            region, name = line.split()
            jobs.append((f"{VHP_BASE}/{region}/{name}", WORK / "vhp" / "png" / name))
    fetch_many(jobs, "vhp (Visible Human Female, about 16.5 GB)")


def tracts() -> None:
    out = WORK / "tracts"
    zip_path = out / "hcp1065_avg_tracts_trk.zip"
    print("tracts: HCP1065 tractography atlas (590 MB) and ICBM 2009a template", flush=True)
    fetch(HCP1065_ZIP, zip_path)
    if not (out / "trk").exists():
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(out / "trk")
    for name in ("tpl-MNI152NLin2009aAsym_res-1_T1w.nii.gz", "tpl-MNI152NLin2009aAsym_res-1_desc-brain_mask.nii.gz"):
        fetch(f"{TEMPLATEFLOW}/{name}", out / name)


def fetal() -> None:
    jobs = []
    dhcp = f"{GIN}/fetal_brain_mri_atlas/raw/master"
    for w in range(21, 37):
        for rel in (f"structural/t2-t{w}.00.nii.gz", f"parcellations/tissue-t{w}.00_dhcp-19.nii.gz",
                    f"transformations/affine-{w}.dof"):
            jobs.append((f"{dhcp}/{rel}", WORK / "fetal_dhcp" / rel))
    for rel in ("README.md", "LICENSE", "datacite.yml", "info/dhcp-atlas-ITKSNAP-19-labels-colour-scheme.txt",
                "info/dhcp-atlas-summary-info-19-labels.csv"):
        jobs.append((f"{dhcp}/{rel}", WORK / "fetal_dhcp" / rel))
    body = f"{GIN}/055t_fetal_mri_atlases/raw/master"
    for w in range(22, 39):
        for rel in (f"t2w-body/t2w-{w}.nii.gz", f"body-organ-labels/labels/label-t2w-{w}.nii.gz"):
            jobs.append((f"{body}/{rel}", WORK / "fetal_body" / rel))
    for rel in ("README.md", "LICENSE", "centiles/body-organ-MRI-centiles-055t.xlsx", "info/055t-body.jpg"):
        jobs.append((f"{body}/{rel}", WORK / "fetal_body" / rel))
    face = f"{GIN}/craniofacial_fetal_mri_atlas/raw/master"
    for rel in ("README.md", "LICENSE", "craniofacial_labels.txt", "fetal-t2w-head-atlas.nii.gz",
                "fetal-t2w-head-label.nii.gz", "fetal-t2w-head-landmarks.nii.gz"):
        jobs.append((f"{face}/{rel}", WORK / "fetal_face" / rel))
    fetch_many(jobs, "fetal (KCL atlases on G-Node GIN)", workers=6)


DATASETS = {"petct": petct, "lung4d": lung4d, "multiplex": multiplex, "vhp": vhp, "tracts": tracts, "fetal": fetal}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("datasets", nargs="+", choices=[*DATASETS, "all"])
    args = ap.parse_args()
    names = list(DATASETS) if "all" in args.datasets else args.datasets
    for name in names:
        DATASETS[name]()
    print("Done:", ", ".join(names))


if __name__ == "__main__":
    sys.exit(main())
