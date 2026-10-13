"""Read a title block: locate it on the page, crop it, and OCR the crop at higher resolution.

Whole-page OCR finds the block but misses its small text; re-reading the crop enlarged picks
it up (ADR 0004). Crop lines are mapped back to page pixels so every value can be highlighted
on the original sheet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image

from revisa.locate import LocateConfig, locate
from revisa.ocr import Box, Line, OcrEngine, lines_from_json, lines_to_json


@dataclass(frozen=True)
class BlockRead:
    """The located title block and the text read from it, in page pixels."""

    box: Box
    anchors: tuple[str, ...]  # keyword lines that placed the block, for reviewers
    lines: tuple[Line, ...]


def read_block(
    image: Image.Image,
    page_lines: list[Line],
    engine: OcrEngine,
    config: LocateConfig,
    *,
    target_width: int = 1600,
    max_upscale: float = 3.0,
) -> BlockRead | None:
    region = locate(page_lines, image.width, image.height, config)
    if region is None:
        return None
    box = region.box
    crop = image.crop((round(box.x0), round(box.y0), round(box.x1), round(box.y1)))
    scale = min(max_upscale, max(1.0, target_width / max(crop.width, 1)))
    if scale > 1.0:
        crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    lines = [
        Line(ln.text, _to_page(ln.box, scale, box), ln.confidence)
        for ln in engine.read(crop)
        if not config.ignore.search(ln.text)
    ]
    return BlockRead(
        box=box, anchors=tuple(a.text for a in region.anchors), lines=tuple(reading_order(lines))
    )


def reading_order(lines: list[Line]) -> list[Line]:
    """Top to bottom, then left to right; lines whose centres are within half a line height
    of each other count as one row."""
    if not lines:
        return []
    height = sorted(ln.box.height for ln in lines)[len(lines) // 2]
    ordered = sorted(lines, key=lambda ln: (ln.box.y0 + ln.box.y1) / 2)
    rows: list[list[Line]] = []
    for line in ordered:
        centre = (line.box.y0 + line.box.y1) / 2
        if rows and abs(centre - _centre(rows[-1][0])) <= height / 2:
            rows[-1].append(line)
        else:
            rows.append([line])
    return [ln for row in rows for ln in sorted(row, key=lambda ln: ln.box.x0)]


def block_to_json(block: BlockRead | None) -> dict[str, Any]:
    if block is None:
        return {"box": None, "anchors": [], "lines": []}
    b = block.box
    return {
        "box": [b.x0, b.y0, b.x1, b.y1],
        "anchors": list(block.anchors),
        "lines": lines_to_json(list(block.lines)),
    }


def block_from_json(data: dict[str, Any]) -> BlockRead | None:
    if data["box"] is None:
        return None
    return BlockRead(
        box=Box(*data["box"]), anchors=tuple(data["anchors"]), lines=tuple(lines_from_json(data["lines"]))
    )


def _to_page(box: Box, scale: float, region: Box) -> Box:
    return Box(box.x0 / scale, box.y0 / scale, box.x1 / scale, box.y1 / scale).offset(region.x0, region.y0)


def _centre(line: Line) -> float:
    return (line.box.y0 + line.box.y1) / 2
