import csv
import io
import json

import pytest

from revisa import cli
from revisa.extract import Found
from revisa.pipeline import SheetResult
from revisa.register import (
    CosmosRegister,
    Entry,
    SqliteRegister,
    check,
    entries_from_run,
    entry_from_result,
    export_csv,
    latest,
)


def entry(sheet_id, number=None, revision=None, *, project="p1", **fields):
    return Entry(
        sheet_id=sheet_id,
        project=project,
        drawing_number=number,
        revision=revision,
        status="accepted",
        **fields,
    )


class FakeContainer:
    """Stands in for an ``azure.cosmos`` container client."""

    def __init__(self):
        self.items = {}
        self.queries = []

    def upsert_item(self, item):
        self.items[item["id"]] = item

    def query_items(self, query, parameters=None, partition_key=None, enable_cross_partition_query=False):
        self.queries.append((query, partition_key, enable_cross_partition_query))
        items = [{**item, "_rid": "x", "_ts": 1} for item in self.items.values()]
        return [i for i in items if partition_key is None or i["project"] == partition_key]


@pytest.fixture(params=["sqlite", "cosmos"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return SqliteRegister(tmp_path / "register.sqlite")
    return CosmosRegister(FakeContainer())


def test_stores_round_trip_and_upsert(store):
    store.upsert(entry("s1", "A-1", project="p1"))
    store.upsert(entry("s2", "A-2", project="p2"))
    store.upsert(entry("s1", "A-1", "B", project="p1"))

    assert [e.sheet_id for e in store.entries()] == ["s1", "s2"]
    assert store.entries("p1")[0].revision == "B"
    assert [e.sheet_id for e in store.entries("p2")] == ["s2"]


def test_cosmos_queries_one_partition_for_a_project():
    container = FakeContainer()
    CosmosRegister(container).entries("p1")

    assert container.queries == [("SELECT * FROM c WHERE c.project = @project", "p1", False)]


def test_later_revisions_supersede_earlier_ones():
    sheets = [entry("s1", "A-19", "A"), entry("s2", "A 19", "C"), entry("s3", "A-19", None)]

    [issue] = check(sheets)

    assert issue.kind == "superseded"
    assert issue.sheet_ids == ["s3", "s1"]
    assert latest(sheets, "a-19").sheet_id == "s2"
    assert latest(sheets, "B-1") is None


def test_numeric_revisions_sort_as_numbers():
    sheets = [entry("s1", "5", "9"), entry("s2", "5", "10")]

    assert latest(sheets, "5").revision == "10"


def test_duplicates_missing_sheets_and_count_conflicts():
    duplicate = check([entry("s1", "A-1", "A"), entry("s2", "A-1", "A")])
    missing = check([entry("s1", sheet_number=1, sheet_count=4), entry("s2", sheet_number=3, sheet_count=4)])
    conflict = check([entry("s1", sheet_count=4), entry("s2", sheet_count=5)])

    assert [i.kind for i in duplicate] == ["duplicate"]
    assert missing[0].detail == "2 of 4 sheets not in the register: 2, 4"
    assert conflict[0].kind == "sheet_count_conflict"
    assert check([entry("s1", sheet_number=1, sheet_count=1)]) == []


def test_entries_keep_evidence_and_export_as_csv():
    result = SheetResult(
        "s1",
        True,
        {
            "drawing_number": Found("A-19", (3, 4), "rule:number-label", 0.9),
            "sheet_count": Found(12, (5,), "r", 1),
        },
        "needs_review",
        ["missing date"],
    )

    made = entry_from_result(result, "techwood")
    rows = list(csv.DictReader(io.StringIO(export_csv([made]))))

    assert made.evidence == {"drawing_number": [3, 4], "sheet_count": [5]}
    assert rows[0]["drawing_number"] == "A-19"
    assert rows[0]["reasons"] == "missing date"


def test_cli_loads_a_run_then_checks_reviews_exports_and_queries(tmp_path, capsys):
    run = tmp_path / "run.json"
    rows = [
        {
            "id": sid,
            "status": status,
            "reasons": reasons,
            "values": {"drawing_number": "A-19", "revision": rev},
            "sources": {"drawing_number": "rule:x"},
            "evidence": {"drawing_number": [1]},
        }
        for sid, status, reasons, rev in (
            ("s1", "accepted", [], "A"),
            ("s2", "needs_review", ["missing date"], "B"),
        )
    ]
    run.write_text(json.dumps({"per_sheet": rows}))
    manifest = tmp_path / "m.jsonl"
    manifest.write_text("")
    db = ["register", "--db", str(tmp_path / "r.sqlite")]

    assert [e.project for e in entries_from_run(run, {"s1": "p"})] == ["p", "unknown"]
    cli.main([*db, "load", str(run), "--manifest", str(manifest)])
    cli.main([*db, "check"])
    cli.main([*db, "review"])
    cli.main([*db, "export"])
    cli.main([*db, "latest", "A-19"])
    out = capsys.readouterr().out

    assert "2 sheets in the register" in out
    assert "superseded: drawing A-19: revision B supersedes A" in out
    assert "s2  A-19  missing date" in out
    assert '"sheet_id": "s2"' in out
    with pytest.raises(SystemExit, match="not in the register"):
        cli.main([*db, "latest", "Z-9"])
