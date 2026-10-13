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

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

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


if __name__ == "__main__":
    main()
