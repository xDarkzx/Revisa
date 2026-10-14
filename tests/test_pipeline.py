from revisa.blocks import BlockRead
from revisa.extract import Found
from revisa.ocr import Box, Line
from revisa.packs.construction import REQUIRED_FIELDS, field_matches
from revisa.pipeline import combine, process

LINES = (Line("x", Box(0, 0, 1, 1), 0.99),)
BLOCK = BlockRead(box=Box(0, 0, 10, 10), anchors=("DATE",), lines=LINES)


def value(v, source="rule:x", confidence=0.95):
    return Found(v, (0,), source, confidence)


def extractor(**fields):
    return lambda lines: dict(fields)


COMPLETE = {"drawing_number": value("A-19"), "title": value("ROOF PLAN"), "date": value("1934-11-22")}


def test_complete_confident_sheet_is_accepted():
    result = process("s", BLOCK, extractor(**COMPLETE), REQUIRED_FIELDS)

    assert (result.status, result.reasons) == ("accepted", [])


def test_every_reason_for_review_is_listed():
    fields = {"title": value("ROOF PLAN", confidence=0.5), "date": value("1934-11-22")}

    result = process("s", BLOCK, extractor(**fields), REQUIRED_FIELDS)

    assert result.status == "needs_review"
    assert result.reasons == ["missing drawing_number", "low OCR confidence on title (0.50)"]


def test_no_title_block_goes_to_review():
    result = process("s", None, extractor(), REQUIRED_FIELDS)

    assert (result.block_found, result.status, result.reasons) == (
        False,
        "needs_review",
        ["no title block found"],
    )


def test_two_readers_agreeing_or_complementing_each_other_are_accepted():
    model = extractor(drawing_number=value("A-19", "llm:m"), title=value("ROOF PLAN", "llm:m"))
    rules = extractor(drawing_number=value("a-19"), date=value("1934-11-22"))

    result = process("s", BLOCK, combine(model, rules, field_matches), REQUIRED_FIELDS)

    assert result.status == "accepted"
    assert result.fields["drawing_number"].source == "llm:m"
    assert result.fields["date"].source == "rule:x"


def test_two_readers_disagreeing_send_the_sheet_to_review():
    model = extractor(**COMPLETE)
    rules = extractor(drawing_number=value("A-91"))

    result = process("s", BLOCK, combine(model, rules, field_matches), REQUIRED_FIELDS)

    assert result.status == "needs_review"
    assert result.reasons == ["readers disagree on drawing_number: 'A-19' vs 'A-91'"]
    assert result.fields["drawing_number"].value == "A-19"
