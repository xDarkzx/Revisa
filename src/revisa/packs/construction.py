"""Construction pack: what a drawing title block contains and how values are compared.

Normalisation exists because the same value is written many ways on real sheets: "Rev. A",
"REV A" and "A" are one revision; "SHEET 1 OF 3" and "1/3" are one sheet index. Scoring
compares normalised values, so the eval measures reading, not formatting.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

# Fields every title block is expected to have and that the eval scores.
SCORED_FIELDS = ("drawing_number", "title", "revision", "sheet_number", "sheet_count", "date", "organisation")


class TitleBlock(BaseModel):
    """Values as printed on the sheet. ``None`` means the sheet doesn't show one."""

    drawing_number: str | None = Field(None, description="The sheet's identifier, e.g. 'A-201' or '5187114'.")
    title: str | None = Field(None, description="Drawing title, e.g. 'First floor plan'.")
    project: str | None = Field(None, description="Building or project name.")
    organisation: str | None = Field(None, description="Agency or firm that issued the drawing.")
    revision: str | None = Field(
        None, description="Latest revision mark in the revision table, e.g. 'A' or '3'."
    )
    revision_date: str | None = Field(None, description="Date against the latest revision.")
    date: str | None = Field(None, description="Date the drawing was issued or approved.")
    sheet_number: int | None = Field(
        None, description="This sheet's position in the set, from 'sheet N of M'."
    )
    sheet_count: int | None = Field(None, description="Number of sheets in the set, from 'sheet N of M'.")
    scale: str | None = None
    drawn_by: str | None = None
    checked_by: str | None = None


# Words that appear in title blocks and rarely elsewhere on a drawing (ADR 0004).
TITLE_BLOCK_KEYWORDS = re.compile(
    # Leading boundary only: OCR often runs words together ("DATENOV.22").
    r"\b(DRAWN|CHECKED|APPROVED|SCALE|SHEET|DATE|REVISIONS?|DRAWING|DWG|DESIGNED|TRACED|SUBMITTED|"
    r"ARCHITECTS?|ENGINEERS?|PROJECT|CONTRACT|SPEC|SIZE|DIVISION)",
    re.IGNORECASE,
)
# Archive stamps added when the drawings were photographed, e.g. "HABS No. GA-2257-5-17".
# OCR misreads them ("HAB5N0.6A-2257"), so match the prefix loosely: HABS, HAER, HALS.
ARCHIVE_STAMP = re.compile(r"\bHA[BEL][S5]", re.IGNORECASE)

Discipline = Literal["architectural", "structural", "mechanical", "electrical", "civil", "plumbing", "other"]


def normalise(field: str, value: object) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip().upper()
    if not text:
        return None
    if field == "revision":
        text = re.sub(r"^(REVISION|REV\.?)\s*", "", text)
    if field == "drawing_number":
        text = re.sub(r"^(DWG\.?|DRAWING)\s*(NO\.?|#)?\s*", "", text)
        text = text.replace(" ", "")
    if field in ("title", "project", "organisation"):
        text = re.sub(r"[^\w& ]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text or None


def field_matches(field: str, expected: object, actual: object) -> bool:
    return normalise(field, expected) == normalise(field, actual)
