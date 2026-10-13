"""Command-line entry point: ``revisa <command>``."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

DEFAULT_MANIFEST = Path("datasets/habs/manifest.jsonl")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="revisa")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("dataset-collect", help="sample public-domain drawings into a manifest")
    collect.add_argument("--total", type=int, default=200)
    collect.add_argument("--per-record", type=int, default=4, help="max sheets from one building record")
    collect.add_argument("--seed", type=int, default=7)
    collect.add_argument("--out", type=Path, default=DEFAULT_MANIFEST)

    download = commands.add_parser("dataset-download", help="download the manifest's sheet images")
    download.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    download.add_argument("--dest", type=Path, default=Path("data/sheets"))
    download.add_argument("--width", type=int, default=3000)

    ocr = commands.add_parser("ocr-pages", help="OCR whole sheets once and cache the lines (local engine)")
    ocr.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ocr.add_argument("--sheets", type=Path, default=Path("data/sheets"))
    ocr.add_argument("--out", type=Path, default=Path("data/ocr/rapidocr/pages"))

    blocks = commands.add_parser("ocr-blocks", help="locate each title block and OCR it enlarged (cached)")
    blocks.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    blocks.add_argument("--sheets", type=Path, default=Path("data/sheets"))
    blocks.add_argument("--pages", type=Path, default=Path("data/ocr/rapidocr/pages"))
    blocks.add_argument("--out", type=Path, default=Path("data/ocr/rapidocr/blocks"))

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.command == "ocr-pages":
        _ocr_pages(args.manifest, args.sheets, args.out)
        return
    if args.command == "ocr-blocks":
        _ocr_blocks(args.manifest, args.sheets, args.pages, args.out)
        return

    from revisa import dataset

    client = dataset.CommonsClient()
    if args.command == "dataset-collect":
        sheets = dataset.collect_sheets(client)
        sample = dataset.stratified_sample(sheets, args.total, args.per_record, args.seed)
        dataset.write_manifest(sample, args.out)
        records = len({s.record for s in sample})
        print(f"{len(sheets)} public-domain sheets found; wrote {len(sample)} from {records} records")
    elif args.command == "dataset-download":
        paths = dataset.download_sheets(client, dataset.read_manifest(args.manifest), args.dest, args.width)
        print(f"{len(paths)} sheets in {args.dest}")


def _ocr_pages(manifest: Path, sheets: Path, out: Path) -> None:
    import json
    import time

    from PIL import Image

    from revisa.dataset import read_manifest
    from revisa.ocr import RapidOcrEngine, lines_to_json

    engine = RapidOcrEngine()
    out.mkdir(parents=True, exist_ok=True)
    for sheet in read_manifest(manifest):
        target = out / f"{sheet.id}.json"
        if target.exists():
            continue
        start = time.perf_counter()
        with Image.open(sheets / f"{sheet.id}.jpg") as image:
            lines = engine.read(image)
        target.write_text(json.dumps(lines_to_json(lines)), encoding="utf-8")
        print(f"{sheet.id}: {len(lines)} lines in {time.perf_counter() - start:.1f}s", flush=True)


def _ocr_blocks(manifest: Path, sheets: Path, pages: Path, out: Path) -> None:
    import json
    import time

    from PIL import Image

    from revisa.blocks import block_to_json, read_block
    from revisa.dataset import read_manifest
    from revisa.ocr import RapidOcrEngine, lines_from_json
    from revisa.packs import construction

    engine = RapidOcrEngine()
    out.mkdir(parents=True, exist_ok=True)
    for sheet in read_manifest(manifest):
        target = out / f"{sheet.id}.json"
        if target.exists():
            continue
        start = time.perf_counter()
        page_lines = lines_from_json(json.loads((pages / f"{sheet.id}.json").read_text(encoding="utf-8")))
        with Image.open(sheets / f"{sheet.id}.jpg") as image:
            block = read_block(image, page_lines, engine, construction.LOCATE)
        target.write_text(json.dumps(block_to_json(block)), encoding="utf-8")
        found = f"{len(block.lines)} lines" if block else "no title block"
        print(f"{sheet.id}: {found} in {time.perf_counter() - start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
