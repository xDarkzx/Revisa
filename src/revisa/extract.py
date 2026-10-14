"""Pack-independent extraction machinery: values tied to the OCR lines they came from.

Every extracted value is a ``Found``: the value, the indices of the OCR lines it was read from,
the rule or model that read it, and the weakest OCR confidence among those lines. Nothing in the
pipeline can produce a value without naming its source lines (ADR 0003).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from revisa.ocr import Line

FieldValue = str | int


@dataclass(frozen=True)
class Found:
    value: FieldValue
    line_ids: tuple[int, ...]
    source: str  # e.g. "rule:date-label" or "llm:gpt-4.1-mini"
    confidence: float  # weakest OCR confidence of the source lines
    note: str | None = None  # why a person should look at this value, if they should


def found(value: FieldValue, lines: Sequence[Line], ids: Sequence[int], source: str) -> Found:
    return Found(value, tuple(ids), source, min(lines[i].confidence for i in ids))


def label_lines(lines: Sequence[Line], label: re.Pattern[str]) -> list[int]:
    return [i for i, line in enumerate(lines) if label.search(line.text)]


def after_label(text: str, label: re.Pattern[str]) -> str:
    """The text that follows the label on the same line, without separators."""
    match = label.search(text)
    if match is None:
        return ""
    return text[match.end() :].strip(" .:;_-")


def neighbours(lines: Sequence[Line], anchor: int, reach: float = 4.0) -> list[int]:
    """Lines a value for the label at ``anchor`` could be in, nearest first.

    Title blocks put values to the right of their label or underneath it. "Near" is measured in
    multiples of the label's own text height, so it works at any resolution.
    """
    label = lines[anchor].box
    unit = max(label.height, 1.0)
    scored: list[tuple[float, int]] = []
    for i, line in enumerate(lines):
        if i == anchor:
            continue
        box = line.box
        overlaps_columns = box.x1 >= label.x0 - unit and box.x0 <= label.x1 + 2 * unit
        same_row = abs((box.y0 + box.y1) / 2 - (label.y0 + label.y1) / 2) <= unit * 0.7
        below = box.y0 >= label.y0 + unit * 0.3
        if same_row and box.x0 >= label.x0:
            distance = max(box.x0 - label.x1, 0.0)
        elif below and overlaps_columns:
            distance = box.y0 - label.y1 + max(label.x0 - box.x0, 0.0) * 0.5
        else:
            continue
        if distance <= reach * unit * 3:
            scored.append((distance, i))
    return [i for _, i in sorted(scored)]


def first_match(
    lines: Sequence[Line],
    anchor: int,
    label: re.Pattern[str],
    accept: Callable[[str], FieldValue | None],
) -> tuple[FieldValue, list[int]] | None:
    """The value on the label's own line if there is one, else in the nearest neighbour."""
    own = accept(after_label(lines[anchor].text, label))
    if own is not None:
        return own, [anchor]
    for i in neighbours(lines, anchor):
        value = accept(lines[i].text)
        if value is not None:
            return value, [anchor, i]
    return None
