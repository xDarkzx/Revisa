"""Command-line entry point: ``revisa <command>``."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

DEFAULT_MANIFEST = Path("datasets/habs/manifest.jsonl")
DEFAULT_LABELS = Path("datasets/habs/labels.jsonl")
SHEETS = Path("data/sheets")
OCR_ROOT = Path("data/ocr")


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("revisa").setLevel(logging.INFO)

    if args.command in ("dataset-collect", "dataset-download"):
        _dataset(args)
    elif args.command in ("ocr-pages", "ocr-blocks"):
        _ocr(args)
    elif args.command == "run":
        _run(args)
    elif args.command == "register":
        _register(args)
    elif args.command == "report":
        from revisa.runs import report as render

        results = [json.loads(path.read_text(encoding="utf-8")) for path in args.results]
        print(render(results, args.split))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="revisa")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("dataset-collect", help="sample public-domain drawings into a manifest")
    collect.add_argument("--total", type=int, default=200)
    collect.add_argument("--per-record", type=int, default=4, help="max sheets from one building record")
    collect.add_argument("--seed", type=int, default=7)
    collect.add_argument("--out", type=Path, default=DEFAULT_MANIFEST)

    download = commands.add_parser("dataset-download", help="download the manifest's sheet images")
    download.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    download.add_argument("--dest", type=Path, default=SHEETS)
    download.add_argument("--width", type=int, default=3000)

    from revisa.runs import OCR_ENGINES, READERS

    for name, help_text in (
        ("ocr-pages", "OCR whole sheets once and cache the lines"),
        ("ocr-blocks", "locate each title block and OCR it enlarged (cached)"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--engine", choices=OCR_ENGINES, default="rapidocr")
        command.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)

    run = commands.add_parser("run", help="extract from cached title blocks and score against the labels")
    run.add_argument("name", help="name for this run, e.g. local-rules")
    run.add_argument("--ocr", choices=OCR_ENGINES, default="rapidocr")
    run.add_argument("--reader", choices=READERS, default="rules")
    run.add_argument("--llm", choices=("ollama", "azure"), default="ollama")
    run.add_argument("--model", help="model or Azure deployment name (default from settings)")
    run.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    run.add_argument("--out", type=Path, default=Path("evals/results"))

    report = commands.add_parser("report", help="markdown table of saved runs")
    report.add_argument("results", type=Path, nargs="+")
    report.add_argument("--split", choices=("test", "dev", "all"), default="test")

    register = commands.add_parser("register", help="the drawing register: load, check, query, export")
    register.add_argument("--store", choices=("sqlite", "cosmos"), default="sqlite")
    register.add_argument("--db", type=Path, default=Path("data/register.sqlite"))
    actions = register.add_subparsers(dest="action", required=True)
    load = actions.add_parser("load", help="load a saved run's sheets into the register")
    load.add_argument("run", type=Path)
    load.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    actions.add_parser("check", help="duplicates, superseded revisions, missing sheets")
    actions.add_parser("review", help="sheets waiting for a person, with reasons")
    actions.add_parser("export", help="the register as CSV")
    latest = actions.add_parser("latest", help="current revision of a drawing")
    latest.add_argument("drawing_number")
    return parser


def _dataset(args: argparse.Namespace) -> None:
    from revisa import dataset

    client = dataset.CommonsClient()
    if args.command == "dataset-collect":
        sheets = dataset.collect_sheets(client)
        sample = dataset.stratified_sample(sheets, args.total, args.per_record, args.seed)
        dataset.write_manifest(sample, args.out)
        records = len({s.record for s in sample})
        print(f"{len(sheets)} public-domain sheets found; wrote {len(sample)} from {records} records")
    else:
        paths = dataset.download_sheets(client, dataset.read_manifest(args.manifest), args.dest, args.width)
        print(f"{len(paths)} sheets in {args.dest}")


def _ocr(args: argparse.Namespace) -> None:
    from revisa import runs
    from revisa.config import Settings
    from revisa.dataset import read_manifest

    settings = Settings()
    engine = runs.make_engine(args.engine, settings)
    interval = settings.azure_ocr_interval if args.engine == "azure" else 0.0
    sheets = read_manifest(args.manifest)
    root = OCR_ROOT / args.engine
    if args.command == "ocr-pages":
        runs.ocr_pages(sheets, SHEETS, engine, root / "pages", interval=interval)
    else:
        runs.ocr_blocks(sheets, SHEETS, root / "pages", engine, out=root / "blocks", interval=interval)


def _run(args: argparse.Namespace) -> None:
    from revisa import runs
    from revisa.config import Settings
    from revisa.evaluate import read_labels
    from revisa.llm import LlmReader
    from revisa.packs import construction

    settings = Settings()
    llm = None
    if args.reader != "rules":
        model = args.model or (
            settings.local_model if args.llm == "ollama" else settings.azure_openai_deployment
        )
        llm = LlmReader(
            runs.llm_client(args.llm, settings),
            model,
            fields=construction.FIELD_GUIDE,
            coerce=construction.coerce,
            cache=Path("data/llm") / args.ocr / model.replace(":", "_").replace("/", "_"),
        )
    result = runs.run(args.name, read_labels(args.labels), OCR_ROOT / args.ocr / "blocks", args.reader, llm)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"{args.name}.json"
    target.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(runs.report([result]))
    print(f"wrote {target}")


def _register(args: argparse.Namespace) -> None:
    from revisa import register as reg
    from revisa.config import Settings

    store: reg.Register
    if args.store == "cosmos":
        endpoint = Settings().azure_cosmos_endpoint
        if not endpoint:
            raise SystemExit("REVISA_AZURE_COSMOS_ENDPOINT is not set")
        store = reg.CosmosRegister.connect(endpoint)
    else:
        args.db.parent.mkdir(parents=True, exist_ok=True)
        store = reg.SqliteRegister(args.db)

    if args.action == "load":
        from revisa.dataset import read_manifest

        projects = {sheet.id: sheet.record for sheet in read_manifest(args.manifest)}
        entries = reg.entries_from_run(args.run, projects)
        for entry in entries:
            store.upsert(entry)
        print(f"{len(entries)} sheets in the register")
    elif args.action == "check":
        issues = reg.check(store.entries())
        for issue in issues:
            print(f"{issue.project}  {issue.kind}: {issue.detail}")
        print(f"{len(issues)} issues")
    elif args.action == "review":
        waiting = [e for e in store.entries() if e.status == "needs_review"]
        for entry in waiting:
            print(f"{entry.sheet_id}  {entry.drawing_number or '-'}  {'; '.join(entry.reasons)}")
        print(f"{len(waiting)} sheets waiting for review")
    elif args.action == "export":
        print(reg.export_csv(store.entries()), end="")
    else:
        found = reg.latest(store.entries(), args.drawing_number)
        if found is None:
            raise SystemExit(f"{args.drawing_number} is not in the register")
        print(found.model_dump_json(indent=1))


if __name__ == "__main__":
    main()
