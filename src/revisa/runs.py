"""Batch jobs behind the CLI: OCR the dataset, run an extraction configuration, report results.

Each stage caches its output under ``data/`` keyed by sheet id, so a configuration can be
re-scored without re-reading anything, and a paid service is called once per sheet, ever.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI, OpenAI
from PIL import Image

from revisa.blocks import block_from_json, block_to_json, read_block
from revisa.config import Settings
from revisa.dataset import Sheet
from revisa.evaluate import Label, score, split_of
from revisa.llm import ChatClient, LlmReader
from revisa.ocr import AzureReadEngine, OcrEngine, RapidOcrEngine, lines_from_json, lines_to_json
from revisa.packs import construction
from revisa.pipeline import Extractor, SheetResult, combine, process

OCR_ENGINES = ("rapidocr", "azure")
READERS = ("rules", "llm", "llm+rules")
REPORT_FIELDS = ("drawing_number", "title", "date", "scale")

log = logging.getLogger(__name__)


def make_engine(name: str, settings: Settings) -> OcrEngine:
    if name == "rapidocr":
        return RapidOcrEngine()
    if not settings.azure_document_intelligence_endpoint:
        raise SystemExit("REVISA_AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT is not set")
    return AzureReadEngine(settings.azure_document_intelligence_endpoint)


def ocr_pages(
    sheets: Iterable[Sheet], images: Path, engine: OcrEngine, out: Path, *, interval: float = 0.0
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for sheet in sheets:
        target = out / f"{sheet.id}.json"
        if target.exists():
            continue
        with _paced(interval), Image.open(images / f"{sheet.id}.jpg") as image:
            lines = engine.read(image)
        target.write_text(json.dumps(lines_to_json(lines)), encoding="utf-8")
        log.info("%s: %d lines", sheet.id, len(lines))


def ocr_blocks(
    sheets: Iterable[Sheet], images: Path, pages: Path, engine: OcrEngine, *, out: Path, interval: float = 0.0
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for sheet in sheets:
        target = out / f"{sheet.id}.json"
        if target.exists():
            continue
        page_lines = lines_from_json(json.loads((pages / f"{sheet.id}.json").read_text(encoding="utf-8")))
        with Image.open(images / f"{sheet.id}.jpg") as image:
            # Only sheets with a title block cost an OCR call, so pace inside read_block's call.
            block = read_block(image, page_lines, _Paced(engine, interval), construction.LOCATE)
        target.write_text(json.dumps(block_to_json(block)), encoding="utf-8")
        log.info("%s: %s", sheet.id, f"{len(block.lines)} lines" if block else "no title block")


@contextmanager
def _paced(interval: float) -> Iterator[None]:
    """Make the enclosed block take at least ``interval`` seconds, for rate-limited services."""
    start = time.monotonic()
    yield
    remaining = interval - (time.monotonic() - start)
    if remaining > 0:
        time.sleep(remaining)


class _Paced:
    """An OCR engine wrapper whose ``read`` takes at least ``interval`` seconds."""

    def __init__(self, engine: OcrEngine, interval: float) -> None:
        self.name = engine.name
        self._engine = engine
        self._interval = interval

    def read(self, image: Image.Image) -> list[Any]:
        with _paced(self._interval):
            return self._engine.read(image)


def llm_client(endpoint: str, settings: Settings) -> ChatClient:
    if endpoint == "ollama":
        return OpenAI(base_url=settings.ollama_url, api_key="ollama")
    if not settings.azure_openai_endpoint:
        raise SystemExit("REVISA_AZURE_OPENAI_ENDPOINT is not set")
    token = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        azure_ad_token_provider=token,
        api_version=settings.azure_openai_api_version,
    )


def run(
    name: str,
    labels: dict[str, Label],
    blocks_dir: Path,
    reader: str,
    llm: LlmReader | None = None,
) -> dict[str, Any]:
    """Process every labelled sheet from cached title-block OCR and score the results."""
    extract: Extractor = construction.read_fields
    if reader != "rules":
        if llm is None:
            raise ValueError(f"reader {reader!r} needs a language model")
        cross_checked = combine(llm, construction.read_fields, construction.field_matches)
        extract = llm if reader == "llm" else cross_checked
    results: list[SheetResult] = []
    start = time.perf_counter()
    for sheet_id in labels:
        block = block_from_json(json.loads((blocks_dir / f"{sheet_id}.json").read_text(encoding="utf-8")))
        if llm is not None:
            llm.sheet_id = sheet_id
        results.append(process(sheet_id, block, extract, construction.REQUIRED_FIELDS))
    seconds = time.perf_counter() - start

    summary = {}
    per_sheet: list[dict[str, Any]] = []
    for split in ("test", "dev", "all"):
        chosen = [r for r in results if split == "all" or split_of(r.sheet_id) == split]
        scored = score(chosen, labels, construction.SCORED_FIELDS, construction.field_matches)
        sheets = scored.pop("per_sheet")
        if split == "all":
            per_sheet = [sheet | {"split": split_of(sheet["id"])} for sheet in sheets]
        summary[split] = scored
    return {
        "name": name,
        "created": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit": _commit(),
        "config": {"ocr": blocks_dir.parent.name, "reader": reader, "model": llm.model if llm else None},
        "usage": _usage(llm, seconds, len(results)),
        "summary": summary,
        "per_sheet": per_sheet,
    }


def _usage(llm: LlmReader | None, seconds: float, sheets: int) -> dict[str, Any]:
    usage: dict[str, Any] = {"seconds": round(seconds, 1), "sheets": sheets}
    if llm is not None:
        usage |= {
            "llm_calls": llm.usage.calls,
            "llm_seconds": round(llm.usage.seconds, 1),
            "prompt_tokens": llm.usage.prompt_tokens,
            "completion_tokens": llm.usage.completion_tokens,
            "ungrounded_values_rejected": len(llm.usage.rejected),
            "rejected": [list(item) for item in llm.usage.rejected],
        }
    return usage


def _commit() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 - git from PATH is intended
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def report(results: Sequence[dict[str, Any]], split: str = "test") -> str:
    """Markdown table of saved runs, for the README."""
    titles = " | ".join(f"{f.replace('_', ' ').capitalize()} read" for f in REPORT_FIELDS)
    rows = [
        f"| Run | OCR | Reader | Sheets fully correct | {titles} | "
        "Errors sent to review | Accepted with an error |",
        "|" + "---|" * (6 + len(REPORT_FIELDS)),
    ]
    for result in results:
        summary = result["summary"][split]
        config = result["config"]
        reader = config["reader"] + (f" ({config['model']})" if config["model"] else "")
        fields = " | ".join(_pct(summary["fields"][f]["recall"]) for f in REPORT_FIELDS)
        routing = summary["routing"]
        rows.append(
            f"| {result['name']} | {config['ocr']} | {reader} | {_pct(summary['sheet_accuracy'])} | "
            f"{fields} | {_pct(routing['error_recall'])} | {_pct(routing['silent_error_rate'])} |"
        )
    return "\n".join(rows)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.0f}%"
