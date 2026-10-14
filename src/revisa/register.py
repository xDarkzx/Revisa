"""The drawing register: one entry per sheet, grouped by project, with set-level checks.

The register is the source of truth for questions like "what's the current revision of A-19?"
(design principle 3). Two stores behave identically: SQLite locally and Azure Cosmos DB
(keyless, partitioned by project) in Azure.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from revisa.pipeline import SheetResult

Status = Literal["accepted", "needs_review"]


class Entry(BaseModel):
    sheet_id: str
    project: str
    drawing_number: str | None = None
    title: str | None = None
    date: str | None = None
    scale: str | None = None
    sheet_number: int | None = None
    sheet_count: int | None = None
    revision: str | None = None
    status: Status
    reasons: list[str] = Field(default_factory=list)
    evidence: dict[str, list[int]] = Field(default_factory=dict)  # field -> OCR line ids
    sources: dict[str, str] = Field(default_factory=dict)  # field -> rule or model that read it


def entry_from_result(result: SheetResult, project: str) -> Entry:
    values: dict[str, Any] = {name: found.value for name, found in result.fields.items()}
    return Entry(
        sheet_id=result.sheet_id,
        project=project,
        status=result.status,
        reasons=result.reasons,
        evidence={name: list(found.line_ids) for name, found in result.fields.items()},
        sources={name: found.source for name, found in result.fields.items()},
        **{name: value for name, value in values.items() if name in Entry.model_fields},
    )


class Register(Protocol):
    def upsert(self, entry: Entry) -> None: ...

    def entries(self, project: str | None = None) -> list[Entry]: ...


class SqliteRegister:
    def __init__(self, path: Path | str) -> None:
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS entries "
            "(sheet_id TEXT PRIMARY KEY, project TEXT NOT NULL, body TEXT NOT NULL)"
        )
        self._db.execute("CREATE INDEX IF NOT EXISTS entries_project ON entries (project)")

    def upsert(self, entry: Entry) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO entries VALUES (?, ?, ?) ON CONFLICT (sheet_id) DO UPDATE "
                "SET project = excluded.project, body = excluded.body",
                (entry.sheet_id, entry.project, entry.model_dump_json()),
            )

    def entries(self, project: str | None = None) -> list[Entry]:
        if project is None:
            rows = self._db.execute("SELECT body FROM entries ORDER BY project, sheet_id")
        else:
            rows = self._db.execute(
                "SELECT body FROM entries WHERE project = ? ORDER BY sheet_id", (project,)
            )
        return [Entry.model_validate_json(body) for (body,) in rows]


class CosmosRegister:
    """Azure Cosmos DB for NoSQL, container partitioned by ``/project`` (infra/main.bicep)."""

    def __init__(self, container: Any) -> None:
        self._container = container

    @classmethod
    def connect(cls, endpoint: str, database: str = "revisa", container: str = "sheets") -> CosmosRegister:
        from azure.cosmos import CosmosClient  # noqa: PLC0415 - only needed in the Azure profile
        from azure.identity import DefaultAzureCredential  # noqa: PLC0415

        client = CosmosClient(endpoint, credential=DefaultAzureCredential())
        return cls(client.get_database_client(database).get_container_client(container))

    def upsert(self, entry: Entry) -> None:
        self._container.upsert_item({"id": entry.sheet_id, **entry.model_dump()})

    def entries(self, project: str | None = None) -> list[Entry]:
        if project is None:
            items = self._container.query_items(
                "SELECT * FROM c ORDER BY c.project", enable_cross_partition_query=True
            )
        else:
            items = self._container.query_items(
                "SELECT * FROM c WHERE c.project = @project",
                parameters=[{"name": "@project", "value": project}],
                partition_key=project,
            )
        return [
            Entry.model_validate({k: v for k, v in item.items() if k in Entry.model_fields}) for item in items
        ]


# --- Set-level checks -------------------------------------------------------------------------


class Issue(BaseModel):
    project: str
    kind: Literal["duplicate", "superseded", "missing_sheets", "sheet_count_conflict"]
    detail: str
    sheet_ids: list[str]


def check(entries: Iterable[Entry]) -> list[Issue]:
    """Problems a document controller looks for across a set of sheets."""
    by_project: dict[str, list[Entry]] = defaultdict(list)
    for entry in entries:
        by_project[entry.project].append(entry)
    issues: list[Issue] = []
    for project, sheets in sorted(by_project.items()):
        issues += _revisions(project, sheets)
        issues += _sequence(project, sheets)
    return issues


def _revisions(project: str, sheets: Sequence[Entry]) -> list[Issue]:
    issues = []
    by_number: dict[str, list[Entry]] = defaultdict(list)
    for sheet in sheets:
        if sheet.drawing_number:
            by_number[_key(sheet.drawing_number)].append(sheet)
    for group in by_number.values():
        number = group[0].drawing_number
        if len(group) < 2:  # noqa: PLR2004 - a pair is the smallest group with a conflict
            continue
        ordered = sorted(group, key=revision_order)
        marks = [revision_order(sheet) for sheet in ordered]
        if len(set(marks)) < len(marks):
            issues.append(
                Issue(
                    project=project,
                    kind="duplicate",
                    detail=f"drawing {number} appears more than once at the same revision",
                    sheet_ids=[s.sheet_id for s in group],
                )
            )
        else:
            latest = ordered[-1]
            issues.append(
                Issue(
                    project=project,
                    kind="superseded",
                    detail=f"drawing {number}: revision {latest.revision or '-'} supersedes "
                    + ", ".join(s.revision or "-" for s in ordered[:-1]),
                    sheet_ids=[s.sheet_id for s in ordered[:-1]],
                )
            )
    return issues


def _sequence(project: str, sheets: Sequence[Entry]) -> list[Issue]:
    counts = {s.sheet_count for s in sheets if s.sheet_count}
    if len(counts) > 1:
        return [
            Issue(
                project=project,
                kind="sheet_count_conflict",
                detail=f"sheets disagree on the set size: {sorted(counts)}",
                sheet_ids=[s.sheet_id for s in sheets if s.sheet_count],
            )
        ]
    if not counts:
        return []
    (total,) = counts
    present = {s.sheet_number for s in sheets if s.sheet_number}
    missing = sorted(set(range(1, total + 1)) - present)
    # A sheet whose own number wasn't read could be any of the missing ones; say nothing.
    if not missing or any(s.sheet_number is None for s in sheets):
        return []
    shown = ", ".join(map(str, missing[:10])) + (" ..." if len(missing) > 10 else "")  # noqa: PLR2004
    return [
        Issue(
            project=project,
            kind="missing_sheets",
            detail=f"{len(missing)} of {total} sheets not in the register: {shown}",
            sheet_ids=[],
        )
    ]


def revision_order(entry: Entry) -> tuple[int, int, str, str]:
    """Sort key for revisions: none < numbers < letters, then by date. "C" > "B", "10" > "9"."""
    mark = (entry.revision or "").strip().upper()
    if not mark:
        return (0, 0, "", entry.date or "")
    if mark.isdigit():
        return (1, int(mark), "", entry.date or "")
    return (2, 0, mark.rjust(3), entry.date or "")


def latest(entries: Iterable[Entry], drawing_number: str) -> Entry | None:
    matches = [e for e in entries if e.drawing_number and _key(e.drawing_number) == _key(drawing_number)]
    return max(matches, key=revision_order) if matches else None


def _key(number: str) -> str:
    """Spacing and separators vary between sheets of one drawing: "A-19", "A 19", "A19"."""
    return re.sub(r"[\s,.\-]", "", number.upper())


EXPORT_FIELDS = (
    "project",
    "drawing_number",
    "title",
    "revision",
    "date",
    "sheet_number",
    "sheet_count",
    "scale",
)


def export_csv(entries: Iterable[Entry]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([*EXPORT_FIELDS, "status", "reasons", "sheet_id"])
    for e in entries:
        writer.writerow(
            [getattr(e, f) or "" for f in EXPORT_FIELDS] + [e.status, "; ".join(e.reasons), e.sheet_id]
        )
    return out.getvalue()


def entries_from_run(path: Path, projects: dict[str, str]) -> list[Entry]:
    """Register entries from a saved run (``revisa run``); ``projects`` maps sheet id to project."""
    rows = json.loads(path.read_text(encoding="utf-8"))["per_sheet"]
    return [
        Entry(
            sheet_id=row["id"],
            project=projects.get(row["id"], "unknown"),
            status=row["status"],
            reasons=row["reasons"],
            evidence=row.get("evidence", {}),
            sources=row["sources"],
            **{name: value for name, value in row["values"].items() if name in Entry.model_fields},
        )
        for row in rows
    ]
