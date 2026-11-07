"""Multiplexed immunofluorescence (CyCIF) slide -> per-marker coloured Deep Zoom pyramids.

Source: HTAN HMS, CyCIF of colorectal cancer (36 markers), DICOM slide microscopy from the NCI Imaging
Data Commons (CC BY 4.0). One reduced-resolution pyramid level (1.3 um/pixel) per marker is used.

Input : work/mif/level4/*.dcm, work/mif/level4_channels.json (marker name -> file),
        both written by `python pipeline/download_data.py multiplex`
Output: work/lakehouse/slides/<id>/channels/<marker>/slide.dzi + slide_files/, thumbnail.jpg, label.json
        and the slide is appended to work/lakehouse/manifest.json by generate_tiles.py (reads label.json).
"""
import json
import math
import os
import pathlib
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pydicom
from PIL import Image
from scipy import ndimage

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "work" / "mif"
OUT = ROOT / "work" / "lakehouse" / "slides"
SLIDE_ID = "colon-cycif"
TILE, OVERLAP, QUALITY = 1022, 1, 85

# The section was imaged for 36 markers; download_data.py fetches only the 8 shown below.
MARKERS_IMAGED = 36

# Marker, colour, shown by default. Chosen to read well together on black.
MARKERS = [
    ("DNA", "#3d7bff", True, "Nuclei (Hoechst)"),
    ("Pan-cytokeratin", "#ffc21a", True, "Tumour and normal epithelium"),
    ("Aortic smooth muscle actin", "#ff3d7f", True, "Smooth muscle and stroma"),
    ("CD45", "#2ee86a", True, "All immune cells"),
    ("CD8a", "#e04bff", False, "Cytotoxic T cells"),
    ("CD68", "#18e3ff", False, "Macrophages"),
    ("Antigen Ki67", "#ffffff", False, "Proliferating cells"),
    ("CD31", "#ff8a1f", False, "Blood vessel endothelium"),
]


def slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-").replace("--", "-")


def read_plane(path: str) -> np.ndarray:
    d = pydicom.dcmread(path)
    frames = d.pixel_array  # (n, 1024, 1024) uint16, TILED_FULL row-major
    cols, rows = d.TotalPixelMatrixColumns, d.TotalPixelMatrixRows
    tw, th = d.Columns, d.Rows
    nx = math.ceil(cols / tw)
    out = np.zeros((math.ceil(rows / th) * th, nx * tw), np.uint16)
    for i, f in enumerate(frames):
        r, c = divmod(i, nx)
        out[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = f
    return out[:rows, :cols]


def stretch(plane: np.ndarray) -> np.ndarray:
    """Background-subtracted, percentile-normalised, gamma 0.8 -> float 0..1."""
    sample = plane[::7, ::7].astype(np.float32)
    lo = np.percentile(sample, 50)  # tissue-free pixels and autofluorescence floor
    hi = np.percentile(sample, 99.8)
    x = (plane.astype(np.float32) - lo) / max(hi - lo, 1.0)
    return np.clip(x, 0, 1) ** 0.8


def hex_rgb(h: str) -> np.ndarray:
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32)


def write_dzi(img: Image.Image, out_dir: pathlib.Path) -> int:
    """Minimal Deep Zoom writer (same layout as OpenSlide's DeepZoomGenerator)."""
    w, h = img.size
    max_level = math.ceil(math.log2(max(w, h)))
    files = out_dir / "slide_files"
    count = 0
    level_img = img
    for level in range(max_level, -1, -1):
        lw, lh = level_img.size
        (files / str(level)).mkdir(parents=True, exist_ok=True)
        for col in range(math.ceil(lw / TILE)):
            for row in range(math.ceil(lh / TILE)):
                x0 = max(col * TILE - OVERLAP, 0)
                y0 = max(row * TILE - OVERLAP, 0)
                x1 = min((col + 1) * TILE + OVERLAP, lw)
                y1 = min((row + 1) * TILE + OVERLAP, lh)
                level_img.crop((x0, y0, x1, y1)).save(files / str(level) / f"{col}_{row}.jpg", "JPEG", quality=QUALITY)
                count += 1
        if level > 0:
            level_img = level_img.resize((max(1, math.ceil(lw / 2)), max(1, math.ceil(lh / 2))), Image.LANCZOS)
    (out_dir / "slide.dzi").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?><Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        f'Format="jpg" Overlap="{OVERLAP}" TileSize="{TILE}"><Size Height="{h}" Width="{w}"/></Image>'
    )
    return count


def build_channel(args) -> dict:
    name, colour, default, meaning, path = args
    s = stretch(read_plane(path))
    rgb = (s[..., None] * hex_rgb(colour)).clip(0, 255).astype(np.uint8)
    cdir = OUT / SLIDE_ID / "channels" / slug(name)
    tiles = write_dzi(Image.fromarray(rgb), cdir)
    small = Image.fromarray(rgb).resize((rgb.shape[1] // 16, rgb.shape[0] // 16), Image.BOX)
    small.save(cdir / "preview.png")
    tile_bytes = sum(p.stat().st_size for p in (cdir / "slide_files").rglob("*.jpg"))
    print(f"{name}: {tiles} tiles", flush=True)
    return {"id": slug(name), "name": name, "meaning": meaning, "color": colour, "visible": default,
            "dzi": f"slides/{SLIDE_ID}/channels/{slug(name)}/slide.dzi",
            "tiles": f"slides/{SLIDE_ID}/channels/{slug(name)}/slide_files",
            "tileCount": tiles, "tilesBytes": tile_bytes}


def main() -> None:
    files = json.loads((SRC / "level4_channels.json").read_text())
    jobs = [(n, c, v, m, str(SRC / files[n])) for n, c, v, m in MARKERS]
    with ProcessPoolExecutor(max_workers=4) as pool:
        channels = list(pool.map(build_channel, jobs))

    d0 = pydicom.dcmread(SRC / files["DNA"], stop_before_pixels=True)
    width, height = int(d0.TotalPixelMatrixColumns), int(d0.TotalPixelMatrixRows)
    mpp = float(d0.SharedFunctionalGroupsSequence[0].PixelMeasuresSequence[0].PixelSpacing[0]) * 1000

    # Composite of the default channels: thumbnail and tour hotspots (dense, mixed-marker regions).
    comp = None
    for ch in channels:
        if not ch["visible"]:
            continue
        p = np.asarray(Image.open(OUT / SLIDE_ID / "channels" / ch["id"] / "preview.png").convert("RGB"), np.float32)
        comp = p if comp is None else comp + p
    comp = comp.clip(0, 255).astype(np.uint8)
    thumb = Image.fromarray(comp)
    thumb.thumbnail((768, 768))
    thumb.save(OUT / SLIDE_ID / "thumbnail.jpg", "JPEG", quality=90)

    energy = ndimage.uniform_filter(comp.astype(np.float32).sum(-1), size=40)
    hs, h_, w_ = [], energy.shape[0], energy.shape[1]
    e = energy.copy()
    for _ in range(4):
        y, x = np.unravel_index(np.argmax(e), e.shape)
        hs.append({"x": round(x / w_, 5), "y": round(y / w_, 5)})
        e[max(0, y - h_ // 6): y + h_ // 6, max(0, x - w_ // 6): x + w_ // 6] = 0
    for f in (OUT / SLIDE_ID / "channels").glob("*/preview.png"):
        f.unlink()

    raw_files = list((SRC / "level4").glob("*.dcm"))
    label = {
        "id": SLIDE_ID,
        "kind": "fluorescence",
        "title": "Colorectal Cancer, 36-plex CyCIF",
        "organ": "Colon",
        "diagnosis": "Colon adenocarcinoma, multiplexed immunofluorescence",
        "blurb": (
            "One tissue section imaged for 36 proteins by cyclic immunofluorescence. Each marker is its own "
            "channel: switch them on and off to see tumour, stroma, nuclei and the immune cells infiltrating it."
        ),
        "project": "HTAN-HMS",
        "case": d0.ContainerIdentifier,
        "sourceFile": f"{len(raw_files)} DICOM instances (one per marker)",
        "gdcFileId": "",
        "source": "Human Tumor Atlas Network (HTAN), Harvard Medical School, via NCI Imaging Data Commons",
        "sourceUrl": "https://portal.imaging.datacommons.cancer.gov/collections/htan_hms/",
        "license": "CC BY 4.0",
        "vendor": "RareCyte CyteFinder",
        "objectivePower": 10.0,
        "mpp": round(mpp, 4),
        "width": width,
        "height": height,
        "levels": math.ceil(math.log2(max(width, height))) + 1,
        "tileSize": TILE,
        "overlap": OVERLAP,
        "format": "jpg",
        "tileCount": sum(c["tileCount"] for c in channels),
        "tilesBytes": sum(c["tilesBytes"] for c in channels),
        "hotspots": hs,
        "rawSizeBytes": sum(p.stat().st_size for p in raw_files),
        "dzi": channels[0]["dzi"],
        "tiles": f"slides/{SLIDE_ID}/channels",
        "thumbnail": f"slides/{SLIDE_ID}/thumbnail.jpg",
        "raw": f"raw/{SLIDE_ID}/",
        "channels": channels,
        "markersAvailable": MARKERS_IMAGED,
    }
    (OUT / SLIDE_ID / "label.json").write_text(json.dumps(label, indent=2))
    print(json.dumps({k: label[k] for k in ("width", "height", "mpp", "tileCount", "hotspots")}))


if __name__ == "__main__":
    os.environ.setdefault("OMP_NUM_THREADS", "2")
    main()
