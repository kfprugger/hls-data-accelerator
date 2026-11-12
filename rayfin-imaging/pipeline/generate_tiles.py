"""Convert whole-slide images (SVS) into Deep Zoom (DZI) tile pyramids + a manifest.

Output layout (mirrors what is uploaded to the Lakehouse `Files/` area):

    <out>/manifest.json
    <out>/slides/<id>/slide.dzi
    <out>/slides/<id>/slide_files/<level>/<col>_<row>.jpg
    <out>/slides/<id>/thumbnail.jpg
    <out>/slides/<id>/label.json   (per-slide metadata)

Usage: python pipeline/generate_tiles.py --raw work/raw --out work/lakehouse [--only brain-gbm]
"""
import argparse
import json
import multiprocessing as mp
import os
import pathlib
import time

import numpy as np
import openslide
from openslide.deepzoom import DeepZoomGenerator
from PIL import Image

HERE = pathlib.Path(__file__).parent
TILE_SIZE = 1022  # + 2 * overlap = 1024 px tiles
OVERLAP = 1
QUALITY = 82

_dz: DeepZoomGenerator | None = None


def _init(path: str) -> None:
    global _dz
    _dz = DeepZoomGenerator(openslide.OpenSlide(path), TILE_SIZE, OVERLAP, limit_bounds=True)


def _write(job: tuple[int, int, int, str]) -> None:
    level, col, row, dest = job
    if os.path.exists(dest):
        return
    tile = _dz.get_tile(level, (col, row)).convert("RGB")
    tile.save(dest, "JPEG", quality=QUALITY, optimize=True, progressive=True)


def whiten(image: Image.Image) -> Image.Image:
    """Turn the slide's glass background pure white so thumbnails sit cleanly on the page."""
    rgb = np.asarray(image, dtype=np.float32) / 255.0
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1e-6)
    glass = (sat < 0.08) & (mx > 0.7)
    white = np.median(rgb[glass], axis=0) if glass.any() else np.ones(3)
    out = np.clip(rgb / np.maximum(white, 1e-3), 0, 1)
    # Feather the near-white, unsaturated pixels to white so uneven illumination disappears.
    omx = out.max(axis=2)
    lift = np.clip((omx - 0.88) / 0.08, 0, 1) * (sat < 0.12)
    out = out + (1 - out) * lift[..., None]
    return Image.fromarray((out * 255).round().astype(np.uint8))


def find_hotspots(thumb: Image.Image, count: int = 5) -> list[dict]:
    """Pick cell-dense (hematoxylin-rich) regions for the guided tour.

    Returns points normalized to image width (OpenSeadragon viewport coordinates).
    """
    rgb = np.asarray(thumb, dtype=np.float32) / 255.0
    h, w, _ = rgb.shape
    mx, mn = rgb.max(axis=2), rgb.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    # Nuclei are dark purple/blue: saturated, darker, and blue >= red * 0.8.
    score = sat * (1.0 - mx) * (rgb[..., 2] >= rgb[..., 0] * 0.8)
    score[(mx > 0.9) | (sat < 0.08)] = 0  # glass / background
    win = max(8, int(min(h, w) * 0.06))
    integral = np.pad(score.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    dens = (integral[win:, win:] - integral[:-win, win:] - integral[win:, :-win] + integral[:-win, :-win]) / win**2
    points = []
    min_dist = max(h, w) * 0.15
    for idx in np.argsort(dens, axis=None)[::-1]:
        y, x = np.unravel_index(idx, dens.shape)
        cy, cx = y + win / 2, x + win / 2
        if dens[y, x] <= 0 or any((cx - p[0]) ** 2 + (cy - p[1]) ** 2 < min_dist**2 for p in points):
            continue
        points.append((cx, cy))
        if len(points) == count:
            break
    return [{"x": round(px / w, 5), "y": round(py / w, 5)} for px, py in points]


def process(slide: dict, raw: pathlib.Path, out: pathlib.Path, workers: int) -> dict:
    src = raw / slide["file"]
    osr = openslide.OpenSlide(str(src))
    dz = DeepZoomGenerator(osr, TILE_SIZE, OVERLAP, limit_bounds=True)
    sdir = out / "slides" / slide["id"]
    files = sdir / "slide_files"
    jobs = []
    for level in range(dz.level_count):
        (files / str(level)).mkdir(parents=True, exist_ok=True)
        cols, rows = dz.level_tiles[level]
        jobs += [(level, c, r, str(files / str(level) / f"{c}_{r}.jpg")) for c in range(cols) for r in range(rows)]

    t0 = time.time()
    with mp.Pool(workers, initializer=_init, initargs=(str(src),)) as pool:
        pool.map(_write, jobs, chunksize=32)

    (sdir / "slide.dzi").write_text(dz.get_dzi("jpg"))
    # The largest single-tile level covers exactly the same (bounds-limited) area as the pyramid.
    thumb_level = max(i for i, t in enumerate(dz.level_tiles) if t == (1, 1))
    thumb = whiten(dz.get_tile(thumb_level, (0, 0)).convert("RGB"))
    thumb.save(sdir / "thumbnail.jpg", "JPEG", quality=88)
    hotspots = find_hotspots(thumb)

    props = osr.properties
    width, height = dz.level_dimensions[-1]
    mpp = props.get(openslide.PROPERTY_NAME_MPP_X)
    entry = {
        **{k: slide[k] for k in ("id", "title", "organ", "diagnosis", "blurb", "project", "case")},
        "sourceFile": slide["file"],
        "gdcFileId": slide["gdcFileId"],
        "source": "NCI Genomic Data Commons, The Cancer Genome Atlas (open access)",
        "sourceUrl": f"https://portal.gdc.cancer.gov/files/{slide['gdcFileId']}",
        "vendor": props.get(openslide.PROPERTY_NAME_VENDOR),
        "objectivePower": float(props.get(openslide.PROPERTY_NAME_OBJECTIVE_POWER) or 0) or None,
        "mpp": float(mpp) if mpp else None,
        "width": width,
        "height": height,
        "levels": dz.level_count,
        "tileSize": TILE_SIZE,
        "overlap": OVERLAP,
        "format": "jpg",
        "tileCount": len(jobs),
        "tilesBytes": sum(os.path.getsize(j[3]) for j in jobs),
        "hotspots": hotspots,
        "rawSizeBytes": src.stat().st_size,
        "dzi": f"slides/{slide['id']}/slide.dzi",
        "tiles": f"slides/{slide['id']}/slide_files",
        "thumbnail": f"slides/{slide['id']}/thumbnail.jpg",
        "raw": f"raw/{slide['file']}",
    }
    (sdir / "label.json").write_text(json.dumps(entry, indent=2))
    print(f"{slide['id']}: {width}x{height}, {dz.level_count} levels, {len(jobs)} tiles in {time.time() - t0:.0f}s", flush=True)
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(HERE.parent / "work" / "raw"))
    ap.add_argument("--out", default=str(HERE.parent / "work" / "lakehouse"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    args = ap.parse_args()
    raw, out = pathlib.Path(args.raw), pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    slides = json.loads((HERE / "slides.json").read_text())
    entries = []
    for s in slides:
        label = out / "slides" / s["id"] / "label.json"
        if args.only and s["id"] not in args.only:
            if label.exists():
                entries.append(json.loads(label.read_text()))
            continue
        entries.append(process(s, raw, out, args.workers))

    # Slides produced by other builders (e.g. build_multiplex.py) carry their own label.json.
    known = {s["id"] for s in slides}
    for label in sorted((out / "slides").glob("*/label.json")):
        extra = json.loads(label.read_text())
        if extra["id"] not in known:
            entries.append(extra)

    manifest = {
        "title": "Rayfin Digital Pathology Atlas",
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "slides": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"manifest: {len(entries)} slides, {sum(e['tileCount'] for e in entries)} tiles")


if __name__ == "__main__":
    main()
