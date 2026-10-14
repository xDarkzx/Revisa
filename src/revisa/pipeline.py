"""From title-block lines to a routed sheet result: accepted, or sent to a person with reasons."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Literal

from revisa.blocks import BlockRead
from revisa.extract import Found
from revisa.ocr import Line

Extractor = Callable[[Sequence[Line]], dict[str, Found]]
Status = Literal["accepted", "needs_review"]

# OCR confidence below which a value is shown to a person rather than trusted.
MIN_CONFIDENCE = 0.8


@dataclass
class SheetResult:
    sheet_id: str
    block_found: bool
    fields: dict[str, Found]
    status: Status
    reasons: list[str] = field(default_factory=list)


def process(
    sheet_id: str,
    block: BlockRead | None,
    extract: Extractor,
    required: Sequence[str],
    min_confidence: float = MIN_CONFIDENCE,
) -> SheetResult:
    if block is None:
        return SheetResult(sheet_id, False, {}, "needs_review", ["no title block found"])
    fields = extract(block.lines)
    reasons = [f"missing {name}" for name in required if name not in fields]
    reasons += [
        f"low OCR confidence on {name} ({value.confidence:.2f})"
        for name, value in fields.items()
        if value.confidence < min_confidence
    ]
    reasons += [value.note for value in fields.values() if value.note]
    return SheetResult(sheet_id, True, fields, "needs_review" if reasons else "accepted", reasons)


def combine(
    primary: Extractor, secondary: Extractor, same: Callable[[str, object, object], bool]
) -> Extractor:
    """Two independent readers. Agreement is kept; a field only one reader found is kept; a
    disagreement keeps the primary value and is flagged for review. ``same`` is the pack's
    notion of equal values (``field_matches``)."""

    def extract(lines: Sequence[Line]) -> dict[str, Found]:
        first, second = primary(lines), secondary(lines)
        merged: dict[str, Found] = {}
        for name in first.keys() | second.keys():
            a, b = first.get(name), second.get(name)
            if a is None:
                merged[name] = b  # type: ignore[assignment]  # one of the two is always present
            elif b is None or same(name, a.value, b.value):
                merged[name] = a
            else:
                note = f"readers disagree on {name}: {a.value!r} vs {b.value!r}"
                merged[name] = replace(a, note=note)
        return merged

    return extract
