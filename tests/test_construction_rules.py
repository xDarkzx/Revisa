import pytest

from revisa.ocr import Box, Line
from revisa.packs.construction import coerce, field_matches, parse_dates, read_fields, title_similarity


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("DATE NOV.22, 1934", ["1934-11-22"]),
        ("Sept. 4,1941", ["1941-09-04"]),
        ("APR:11 1902", ["1902-04-11"]),
        ("Submitted 13 Oct 1938", ["1938-10-13"]),
        ("DATE 7/12/44", ["1944-07-12"]),
        ("7-21-65 and 8.10.66", ["1965-07-21", "1966-08-10"]),
        ("May 1900", ["1900-05"]),
        ("FEB 1902 B-687", ["1902-02"]),
        ("JUNE 1.1915", ["1915-06-01"]),
    ],
)
def test_dates_are_read_to_the_precision_printed(text, expected):
    assert parse_dates(text) == expected


@pytest.mark.parametrize("text", ["13/45/34", "SHEET 18 OF 35", "106-A-4", '1/8" = 1\'-0"'])
def test_things_that_are_not_dates(text):
    assert parse_dates(text) == []


def test_two_digit_years_use_the_pack_century():
    assert parse_dates("5/5/26", century=2000) == ["2026-05-05"]


def line(text, x, y, h=20, *, w=None, confidence=0.95):
    return Line(text, Box(x, y, x + (w or 12 * len(text)), y + h), confidence)


# A Techwood-style block: labels with values beside or under them, title in the largest lettering.
BLOCK = [
    line("REVISIONS", 0, 0),
    line("TECHWOOD PROJECT NO. 1101", 300, 0, h=34),
    line("PUBLIC WORKS ADMINISTRATION-HOUSING DIVISION", 300, 40),
    line("DRAWN BY L.W.W.", 0, 100),
    line("CHECKED BY G.B.", 0, 130),
    line("DATE NOV. 22, 1934", 0, 160),
    line("REVISED 3-1-35", 0, 190),
    line("DWG. NO.", 600, 100),
    line("A-19", 600, 125, h=30),
    line("SCALE", 800, 100),
    line('1/16" = 1\'-0"', 800, 125),
    line("SHEET 4 OF 12", 800, 160),
]


def test_rules_read_a_typical_block_with_evidence():
    fields = read_fields(BLOCK)

    assert fields["drawing_number"].value == "A-19"
    assert fields["drawing_number"].line_ids == (7, 8)  # the label and the value
    assert fields["date"].value == "1934-11-22"  # not the later revision date
    assert fields["scale"].value == '1/16" = 1\'-0"'
    assert (fields["sheet_number"].value, fields["sheet_count"].value) == (4, 12)
    assert fields["title"].value == "TECHWOOD PROJECT NO. 1101"
    assert all(f.source.startswith("rule:") for f in fields.values())


def test_unlabelled_identifier_is_used_when_nothing_is_labelled():
    fields = read_fields([line("ARMORY", 0, 0, h=40), line("106-A-4", 0, 60, h=50), line("SCALE-1", 0, 120)])

    assert fields["drawing_number"].value == "106-A-4"
    assert fields["drawing_number"].source == "rule:standalone-id"


def test_sheet_number_alone_and_empty_blocks():
    assert read_fields([line("SHEET NO. 88", 0, 0)])["sheet_number"].value == 88
    assert read_fields([]) == {}


def test_scale_label_with_value_beside_it_and_no_title_candidates():
    fields = read_fields([line("SCALE AS NOTED", 0, 0), line("DRAWN BY X", 0, 40)])

    assert fields["scale"].value == "AS NOTED"
    assert "title" not in fields


@pytest.mark.parametrize(
    ("field", "text", "expected"),
    [
        ("date", "DATE 7/12/44", "1944-07-12"),
        ("date", "no date here", None),
        ("sheet_number", "SHEET 14", 14),
        ("sheet_count", "A-19", None),
        ("drawing_number", "Y & D DRAWING NO. 323374", "323374"),
        ("scale", "SCALE: 1/8\" = 1'", "1/8\" = 1'"),
        ("title", "  PLAN   OF STABLE ", "PLAN OF STABLE"),
    ],
)
def test_model_values_are_coerced_to_register_form(field, text, expected):
    assert coerce(field, text) == expected


def test_titles_match_on_word_overlap():
    assert field_matches("title", "Plan of stable", "PLAN OF STABLE BLDG 88")
    assert not field_matches("title", "Plan of stable", "ROOF FRAMING")
    assert title_similarity(None, None) == 1.0
    assert title_similarity("Roof", None) == 0.0


RDQ, RSQ = chr(0x201D), chr(0x2019)  # typographic quotes OCR returns


def test_scales_match_whatever_the_quote_characters():
    assert field_matches("scale", '1/16" = 1\'-0"', "1/16" + RDQ + " = 1" + RSQ + "-0" + RDQ)
