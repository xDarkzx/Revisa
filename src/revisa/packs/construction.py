"""Construction pack: what a drawing title block contains, how to read it, how to score it.

Normalisation exists because the same value is written many ways on real sheets: "Rev. A",
"REV A" and "A" are one revision; `1/16" = 1'-0"` and `1/16=1-0` are one scale. Scoring
compares normalised values, so the eval measures reading, not formatting.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from revisa.extract import FieldValue, Found, found, label_lines, neighbours
from revisa.locate import LocateConfig
from revisa.ocr import Line

# Fields the labelled dataset records and the eval scores (datasets/habs/README.md).
SCORED_FIELDS = ("drawing_number", "title", "date", "scale", "sheet_number", "sheet_count", "revision")
# A sheet missing any of these is sent to review: the register can't file it without them.
REQUIRED_FIELDS = ("drawing_number", "title", "date")


class TitleBlock(BaseModel):
    """Values as printed on the sheet. ``None`` means the sheet doesn't show one."""

    drawing_number: str | None = Field(None, description="The sheet's identifier, e.g. 'A-201' or '5187114'.")
    title: str | None = Field(None, description="Drawing title, e.g. 'First floor plan'.")
    date: str | None = Field(None, description="Date the drawing was made or approved, ISO 8601.")
    scale: str | None = None
    sheet_number: int | None = Field(None, description="This sheet's position, from 'sheet N of M'.")
    sheet_count: int | None = Field(None, description="Sheets in the set, from 'sheet N of M'.")
    revision: str | None = Field(None, description="Latest revision mark in the revision table.")


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

LOCATE = LocateConfig(keywords=TITLE_BLOCK_KEYWORDS, ignore=ARCHIVE_STAMP)

Discipline = Literal["architectural", "structural", "mechanical", "electrical", "civil", "plumbing", "other"]

# --- Reading dates ----------------------------------------------------------------------------

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip
_MONTH = r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\.?"
_DAY = r"(\d{1,2})(?:ST|ND|RD|TH)?"
_YEAR = r"(\d{4}|'?\d{2})"
_SHORT_YEAR = 2  # digits in a year written like '34
# Years a construction drawing can plausibly carry; OCR turns "1977" into "1077" otherwise.
YEARS = range(1700, 2101)
_DATE_FORMS = [
    # month day year, e.g. NOV. 22, 1934 / Sept. 4,1941 / APR:11 1902
    ("mdy", re.compile(rf"\b{_MONTH}[\s:.,]*{_DAY}[\s,.]+{_YEAR}\b")),
    # day month year, e.g. 13 Oct 1938 / 12 June 69
    ("dmy", re.compile(rf"\b{_DAY}[\s.]*{_MONTH}[\s,.]*{_YEAR}\b")),
    # numeric month/day/year, e.g. 11/22/34 / 7-21-65 / 2.5.45
    ("num", re.compile(r"(?<![\d/.-])(\d{1,2})\s?[/.-]\s?(\d{1,2})\s?[/.-]\s?(\d{4}|\d{2})(?![\d/-])")),
    # month and year only, e.g. May 1900 / FEB 1902
    ("my", re.compile(rf"\b{_MONTH}[\s,.]*(\d{{4}})\b")),
]


def parse_dates(text: str, century: int = 1900) -> list[str]:
    """Every date in ``text`` as ISO 8601, to the precision printed ("1934-11-22", "1900-05").

    Two-digit years are read as ``century`` + year; US month/day order is assumed for numeric
    dates. Both are pack settings because they depend on where and when drawings were made.
    """
    upper = text.upper()
    found_dates: list[tuple[int, str]] = []
    taken: list[range] = []
    for form, pattern in _DATE_FORMS:
        for match in pattern.finditer(upper):
            if any(match.start() in span for span in taken):
                continue
            iso = _to_iso(form, match.groups(), century)
            if iso is not None:
                found_dates.append((match.start(), iso))
                taken.append(range(match.start(), match.end()))
    return [iso for _, iso in sorted(found_dates)]


def _to_iso(form: str, groups: Sequence[str], century: int) -> str | None:
    if form == "my":
        month, year = _MONTHS[groups[0][:3]], _year(groups[1], century)
        return f"{year:04d}-{month:02d}" if year in YEARS else None
    if form == "mdy":
        month, day, year = _MONTHS[groups[0][:3]], int(groups[1]), _year(groups[2], century)
    elif form == "dmy":
        day, month, year = int(groups[0]), _MONTHS[groups[1][:3]], _year(groups[2], century)
    else:
        month, day, year = int(groups[0]), int(groups[1]), _year(groups[2], century)
    if year not in YEARS:
        return None
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _year(text: str, century: int) -> int:
    digits = text.lstrip("'")
    return century + int(digits) if len(digits) <= _SHORT_YEAR else int(digits)


# --- Reading fields with rules ----------------------------------------------------------------

DATE_LABEL = re.compile(r"\b(DATE|DATED|DRAWN|APPROVED|SUBMITTED|MADE)\b", re.IGNORECASE)
# Dates on these lines are revisions, issues or archive handling, not the drawing's own date.
NOT_DRAWING_DATE = re.compile(
    r"REVIS|\bREV\b|AS[- ]?BUILT|RECORD|MICROFILM|PHOTO|\bEAM\b|ISSUED|PRINTED|FILMSORT|CORRECTED|BROUGHT",
    re.IGNORECASE,
)
# OCR reads "NO." as N2, Nº, NS, Ne, N° and "DRAWING" as DRAVING or DROWING, so both are loose.
_NO = r"(?:N[O0ºoSs2e°Q9]\b\.?|NUMBER|#)"
NUMBER_LABEL = re.compile(
    r"\b(?:DR[AO][WV][IL1]NGS?|DRWG|DWG|DR|PLAN|FILE|INDEX)\.?\s*" + _NO + r"|\bDWG\.?\s*$",
    re.IGNORECASE,
)
ID_LENGTH = (2, 16)  # characters in a drawing number
IDENTIFIER = re.compile(r"^(?=[A-Z0-9 .,/-]*\d)[A-Z]{0,4}[ .-]?[A-Z0-9][A-Z0-9 ,./-]{0,13}$")
# A line that is nothing but a structured identifier ("C-3565", "106-A-4", "6899-800").
# The first part can't be a word ("SCALE-1", "SPAN-1"): those are labels, not identifiers.
STANDALONE_ID = re.compile(r"^(?=.*\d)(?=.*-)(?![A-Z]{4,}-)[A-Z0-9]{1,6}(?:-[A-Z0-9]{1,5}){1,3}$")
SHEET_OF = [
    re.compile(r"SHEET\s*(?:NO\.?\s*)?(\d{1,3})\s*OF\s*(\d{1,3})", re.IGNORECASE),
    re.compile(r"\b(\d{1,3})\s*OF\s*(\d{1,3})\s*SHEETS", re.IGNORECASE),
]
SHEET_ONLY = re.compile(r"SHEET\s*NO\.?\s*(\d{1,3})\b", re.IGNORECASE)
SCALE_LABEL = re.compile(r"\bSCALE[S]?\b", re.IGNORECASE)
SCALE_VALUE = re.compile(
    # The u2019 and u201d escapes are the typographic quotes OCR returns for feet and inches marks.
    r"(\d[\d /]*[\"\u201d'\u2019]?\s*=\s*\d[\d\s'\u2019\"\u201d.-]*(FT|FOOT|FEET)?|AS\s+(NOTED|SHOWN)|"
    r"NOTED|SHOWN|FULL\s+SIZE|"
    r"\d+\s+(FEET|FT)\.?\s+(TO|PER|=)\s+(AN|ONE|1)?\s*INCH)",
    re.IGNORECASE,
)
# Lines that are field labels or block furniture, never part of the drawing's title.
NOT_TITLE = re.compile(
    r"\b(DRAWN|CHECKED|APPROVED|TRACED|SCALE|SHEET|DATE|REVISION|DESIGNED|SUBMITTED|SPEC|"
    r"DRAWING NO|DWG|CONTRACT|ENGINEER|ARCHITECT|DEPARTMENT|BUREAU|OFFICE|DIVISION|CHIEF|"
    r"OFFICER|MICROFILM|FOR\b|BY\b)",
    re.IGNORECASE,
)


def read_fields(lines: Sequence[Line], century: int = 1900) -> dict[str, Found]:
    """Deterministic extraction from title-block OCR lines. Fields it can't settle are absent."""
    fields: dict[str, Found] = {}
    for name, value in (
        ("drawing_number", _drawing_number(lines)),
        ("date", _date(lines, century)),
        ("scale", _scale(lines)),
        ("title", _title(lines)),
    ):
        if value is not None:
            fields[name] = value
    fields.update(_sheet_of(lines))
    return fields


def _identifier(text: str) -> str | None:
    candidate = re.sub(r"\s+", " ", text.upper()).strip(" .:;_")
    short, long = ID_LENGTH
    if not short <= len(candidate) <= long or not IDENTIFIER.match(candidate) or parse_dates(candidate):
        return None
    return candidate


def _drawing_number(lines: Sequence[Line]) -> Found | None:
    return _labelled_number(lines) or _standalone_number(lines)


def _standalone_number(lines: Sequence[Line]) -> Found | None:
    """No label: the most prominent line that is only an identifier. Weaker evidence, so the
    source says so and a reviewer sees it."""
    candidates = [
        i
        for i, line in enumerate(lines)
        if STANDALONE_ID.match(line.text.strip().upper().rstrip("."))
        and not parse_dates(line.text)
        and not SCALE_VALUE.search(line.text)
    ]
    if not candidates:
        return None
    best = max(candidates, key=lambda i: lines[i].box.height)
    return found(lines[best].text.strip().upper().rstrip("."), lines, [best], "rule:standalone-id")


def _labelled_number(lines: Sequence[Line]) -> Found | None:
    for anchor in label_lines(lines, NUMBER_LABEL):
        own = NUMBER_LABEL.split(lines[anchor].text, maxsplit=1)[-1]
        value = _identifier(own)
        if value is not None:
            return found(value, lines, [anchor], "rule:number-label")
        for i in neighbours(lines, anchor):
            value = _identifier(lines[i].text)
            if value is not None:
                return found(value, lines, [anchor, i], "rule:number-label")
    return None


def _date(lines: Sequence[Line], century: int) -> Found | None:
    candidates: list[tuple[int, str, list[int]]] = []
    labelled = set(label_lines(lines, DATE_LABEL))
    near_label = {n for i in labelled for n in neighbours(lines, i)[:2]}
    for i, line in enumerate(lines):
        if NOT_DRAWING_DATE.search(line.text):
            continue
        for iso in parse_dates(line.text, century):
            score = 2 if i in labelled else 1 if i in near_label else 0
            candidates.append((score, iso, [i]))
    if not candidates:
        return None
    # Best-labelled first; among equals the earliest, since revisions and approvals come later.
    score, iso, ids = min(candidates, key=lambda c: (-c[0], c[1]))
    return found(iso, lines, ids, f"rule:date-{('unlabelled', 'near-label', 'label')[score]}")


def _scale(lines: Sequence[Line]) -> Found | None:
    for anchor in label_lines(lines, SCALE_LABEL):
        rest = SCALE_LABEL.split(lines[anchor].text, maxsplit=1)[-1]
        match = SCALE_VALUE.search(rest)
        if match:
            return found(match.group(0).strip(), lines, [anchor], "rule:scale-label")
        for i in neighbours(lines, anchor)[:3]:
            match = SCALE_VALUE.search(lines[i].text)
            if match:
                return found(match.group(0).strip(), lines, [anchor, i], "rule:scale-label")
    return None


def _sheet_of(lines: Sequence[Line]) -> dict[str, Found]:
    for i, line in enumerate(lines):
        for pattern in SHEET_OF:
            match = pattern.search(line.text)
            if match and 0 < int(match.group(1)) <= int(match.group(2)):
                return {
                    "sheet_number": found(int(match.group(1)), lines, [i], "rule:sheet-of"),
                    "sheet_count": found(int(match.group(2)), lines, [i], "rule:sheet-of"),
                }
        match = SHEET_ONLY.search(line.text)
        if match and int(match.group(1)) > 0:
            return {"sheet_number": found(int(match.group(1)), lines, [i], "rule:sheet-no")}
    return {}


TITLE_MIN_CONFIDENCE = 0.8  # misread lines make poor titles


def _title(lines: Sequence[Line]) -> Found | None:
    """The largest lettering in the block that isn't a label, joined with stacked lines of the
    same size. Titles are lettered biggest on most sheets; this is the baseline a language model
    has to beat."""
    words = [
        i
        for i, line in enumerate(lines)
        if re.search(r"[A-Za-z]{3,}", line.text)
        and not NOT_TITLE.search(line.text)
        and not parse_dates(line.text)
        and line.confidence >= TITLE_MIN_CONFIDENCE
    ]
    if not words:
        return None
    biggest = max(words, key=lambda i: lines[i].box.height)
    height = lines[biggest].box.height
    group = [biggest]
    for i in sorted(words, key=lambda i: lines[i].box.y0):
        box = lines[i].box
        if i in group or not 0.75 * height <= box.height <= 1.33 * height:
            continue
        gap = min(abs(box.y0 - lines[g].box.y1) for g in group)
        same_column = any(box.x1 > lines[g].box.x0 and box.x0 < lines[g].box.x1 for g in group)
        if same_column and gap <= 1.5 * height:
            group.append(i)
    group.sort(key=lambda i: lines[i].box.y0)
    text = " ".join(lines[i].text.strip() for i in group)
    return found(text, lines, group, "rule:largest-lettering")


# --- Scoring ----------------------------------------------------------------------------------

# Titles are long and their extent is a judgement call ("FLOOR PLAN" vs "FIRST FLOOR PLAN BLDG 19"),
# so a title counts as read when its words overlap the label's by at least this Jaccard index.
TITLE_MATCH = 0.5


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
        text = re.sub(r"[\s,.]", "", text)
    if field == "scale":
        text = re.sub(r"[\s\"'\u201d\u2019`.]", "", text)
        text = text.replace("FEET", "FT").replace("FOOT", "FT")
    if field == "title":
        text = re.sub(r"[^\w& ]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text or None


def field_matches(field: str, expected: object, actual: object) -> bool:
    if field == "title":
        return title_similarity(expected, actual) >= TITLE_MATCH
    return normalise(field, expected) == normalise(field, actual)


def title_similarity(expected: object, actual: object) -> float:
    a = set((normalise("title", expected) or "").split())
    b = set((normalise("title", actual) or "").split())
    if not a or not b:
        return 1.0 if a == b else 0.0
    return len(a & b) / len(a | b)


# --- Reading fields with a language model -----------------------------------------------------

# What each field means, for the model. Kept here because it's part of the pack, not the core.
FIELD_GUIDE = {
    "drawing_number": (
        "the sheet's own identifier: drawing, plan, sheet or file number such as 'A-19', '6899-480' "
        "or '323374'. Not project, contract, job, specification or order numbers, and never an "
        "archive stamp beginning HABS or HAER."
    ),
    "title": (
        "what the drawing is, as lettered in the block: the building or project name and the "
        "subject, e.g. 'PLAN OF STABLE' or 'DISPENSARY SICK OFFICERS QUARTERS'."
    ),
    "date": (
        "the date the drawing was made, drawn, submitted or approved. Not a revision date, an "
        "'as built' or record date, or a microfilm or archive stamp."
    ),
    "scale": "the scale as printed, e.g. '1/8\" = 1'-0\"' or 'AS NOTED'.",
    "sheet_number": "this sheet's number in the set, from 'SHEET n OF m' or 'SHEET NO. n'.",
    "sheet_count": "the number of sheets in the set, from 'SHEET n OF m'.",
    "revision": "the latest revision mark (a letter or number) in the revision table; null if it is empty.",
}


MAX_LABEL_PREFIX = 12  # characters allowed before a label, e.g. 'Y & D '


def coerce(field: str, text: str, century: int = 1900) -> FieldValue | None:
    """Turn a value as printed into the register's form; ``None`` if it isn't one."""
    text = text.strip()
    if field == "date":
        dates = parse_dates(text, century)
        return dates[0] if dates else None
    if field in ("sheet_number", "sheet_count"):
        digits = re.fullmatch(r"(?:SHEETS?\b|N[O0]\b\.?|OF\b|#|\s)*(\d{1,3})\.?", text, flags=re.IGNORECASE)
        return int(digits.group(1)) if digits else None
    text = re.sub(r"\s+", " ", text)
    # Models sometimes copy the label with the value ("Y & D DRAWING NO. 323374", "SCALE 1/8").
    label = {"drawing_number": NUMBER_LABEL, "scale": SCALE_LABEL}.get(field)
    match = label.search(text) if label else None
    if match and match.start() <= MAX_LABEL_PREFIX:
        text = text[match.end() :]
    return text.strip(" .:;") or None
