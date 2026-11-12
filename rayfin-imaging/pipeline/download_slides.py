"""Download the curated TCGA whole-slide images listed in slides.json from the GDC.

Usage: python pipeline/download_slides.py [--out work/raw]
"""
import argparse
import json
import pathlib
import shutil
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).parent
GDC_DATA = "https://api.gdc.cancer.gov/data/"


def fetch(slide: dict, out: pathlib.Path) -> str:
    dest = out / slide["file"]
    if dest.exists() and dest.stat().st_size > 0:
        return f"skip {dest.name}"
    tmp = dest.with_suffix(".part")
    for attempt in range(1, 6):
        try:
            req = urllib.request.Request(GDC_DATA + slide["gdcFileId"], headers={"User-Agent": "rayfin-imaging-pipeline"})
            with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tmp.rename(dest)
            return f"done {dest.name}"
        except Exception as exc:
            if attempt == 5:
                raise
            time.sleep(5 * attempt)
    return f"done {dest.name}"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE.parent / "work" / "raw"))
    ap.add_argument("--only", nargs="*", help="Only download slide IDs listed here")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    slides = json.loads((HERE / "slides.json").read_text())
    if args.only:
        slides = [s for s in slides if s["id"] in args.only]
    with ThreadPoolExecutor(3) as pool:
        for msg in pool.map(lambda s: fetch(s, out), slides):
            print(msg)


if __name__ == "__main__":
    main()
