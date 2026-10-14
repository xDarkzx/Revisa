"""Score sheet results against the labelled dataset.

Per field, each sheet is one of: ``correct``; ``missed`` (printed on the sheet, not extracted);
``wrong`` (extracted, but not what the sheet says); ``invented`` (extracted, but the sheet shows
no such value); ``absent`` (neither printed nor extracted, also correct). Fields a labeller
marked illegible aren't scored. A sheet is correct when every scored field is.

The headline is not only accuracy: it's how many wrong sheets were caught by review, because a
flagged error costs a person seconds and a silent one ends up in the register.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from revisa.pipeline import SheetResult

Matcher = Callable[[str, object, object], bool]


class Label(BaseModel):
    id: str
    title_block: bool
    drawing_number: list[str] | None
    title: list[str] | None
    date: list[str] | None
    scale: list[str] | None
    sheet_number: list[int] | None
    sheet_count: list[int] | None
    revision: list[str] | None
    illegible: list[str]
    note: str

    def accepted(self, field: str) -> list[Any] | None:
        """Every value the sheet can fairly be read as; ``None`` when it shows none."""
        value: list[Any] | None = getattr(self, field)
        return value


Split = Literal["dev", "test"]


def split_of(sheet_id: str) -> Split:
    """Half the sheets are for developing rules and prompts, half are held out for reporting.

    Hash-based so the assignment is fixed, needs no stored list, and new sheets slot in. Every
    sheet comes from a different building record, so the halves share no drawing sets.
    """
    return "dev" if int(hashlib.sha256(sheet_id.encode()).hexdigest(), 16) % 2 == 0 else "test"


def read_labels(path: Path) -> dict[str, Label]:
    rows = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return {label.id: label for label in (Label.model_validate(row) for row in rows)}


def outcome(field: str, label: Label, result: SheetResult, same: Matcher) -> str | None:
    if field in label.illegible:
        return None
    expected = label.accepted(field)
    found = result.fields.get(field)
    if expected is None:
        return "absent" if found is None else "invented"
    if found is None:
        return "missed"
    return "correct" if any(same(field, value, found.value) for value in expected) else "wrong"


def score(
    results: Sequence[SheetResult], labels: dict[str, Label], fields: Sequence[str], same: Matcher
) -> dict[str, Any]:
    per_sheet = []
    per_field: dict[str, Counter[str]] = {name: Counter() for name in fields}
    for result in results:
        label = labels[result.sheet_id]
        outcomes = {name: outcome(name, label, result, same) for name in fields}
        for name, value in outcomes.items():
            if value is not None:
                per_field[name][value] += 1
        correct = all(value in (None, "correct", "absent") for value in outcomes.values())
        per_sheet.append(
            {
                "id": result.sheet_id,
                "correct": correct,
                "status": result.status,
                "reasons": result.reasons,
                "outcomes": outcomes,
                "values": {name: found.value for name, found in result.fields.items()},
                "sources": {name: found.source for name, found in result.fields.items()},
                "block_found": result.block_found,
                "label_has_block": label.title_block,
            }
        )
    return {
        "sheets": len(per_sheet),
        "fields": {name: _field_summary(counts) for name, counts in per_field.items()},
        "sheet_accuracy": _ratio(sum(bool(s["correct"]) for s in per_sheet), len(per_sheet)),
        "routing": _routing(per_sheet),
        "locator": _locator(per_sheet),
        "per_sheet": per_sheet,
    }


def _field_summary(counts: Counter[str]) -> dict[str, Any]:
    printed = counts["correct"] + counts["missed"] + counts["wrong"]
    extracted = counts["correct"] + counts["wrong"] + counts["invented"]
    return {
        "counts": dict(counts),
        # Of the values printed on sheets, the share read correctly.
        "recall": _ratio(counts["correct"], printed),
        # Of the values extracted, the share that are right.
        "precision": _ratio(counts["correct"], extracted),
    }


def _routing(per_sheet: list[dict[str, Any]]) -> dict[str, Any]:
    wrong = [s for s in per_sheet if not s["correct"]]
    review = [s for s in per_sheet if s["status"] == "needs_review"]
    accepted = [s for s in per_sheet if s["status"] == "accepted"]
    silent = [s for s in accepted if not s["correct"]]
    return {
        "accepted": len(accepted),
        "needs_review": len(review),
        # Of the sheets with any error, the share a person was asked to check.
        "error_recall": _ratio(len(wrong) - len(silent), len(wrong)),
        # Of the sheets sent to a person, the share that really had an error.
        "review_precision": _ratio(sum(not s["correct"] for s in review), len(review)),
        # Of the sheets accepted without review, the share with an error nobody was told about.
        "silent_error_rate": _ratio(len(silent), len(accepted)),
        "accepted_correct": len(accepted) - len(silent),
    }


def _locator(per_sheet: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = Counter((s["label_has_block"], s["block_found"]) for s in per_sheet)
    return {
        "found_when_present": _ratio(pairs[(True, True)], pairs[(True, True)] + pairs[(True, False)]),
        "found_when_absent": pairs[(False, True)],
        "absent_sheets": pairs[(False, True)] + pairs[(False, False)],
    }


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None
