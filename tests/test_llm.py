import json
from types import SimpleNamespace

from revisa.llm import LlmReader, grounded, instructions, listing
from revisa.ocr import Box, Line
from revisa.packs.construction import FIELD_GUIDE, coerce

LINES = [
    Line("DWG. NO.", Box(0, 0, 80, 20), 0.99),
    Line("A-19", Box(0, 30, 50, 60), 0.9),
    Line("DATE NOV. 22, 1934", Box(100, 0, 300, 20), 0.97),
    Line("TECHWOOD PROJECT NO. 1101", Box(100, 30, 400, 70), 0.98),
]


def pick(ids, text):
    return {"line_ids": ids, "text": text}


def answer(**fields):
    picks = {name: pick([], None) for name in FIELD_GUIDE}
    picks.update(fields)
    return picks


class FakeChat:
    """Stands in for ``openai.OpenAI``: returns canned JSON and records requests."""

    def __init__(self, content):
        self.content = content
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **request):
        self.requests.append(request)
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def reader(client, cache=None):
    llm = LlmReader(client, "test-model", fields=FIELD_GUIDE, coerce=coerce, cache=cache)
    llm.sheet_id = "sheet1"
    return llm


def test_grounded_values_are_kept_with_their_lines():
    client = FakeChat(
        json.dumps(
            answer(
                drawing_number=pick([1], "A-19"),
                date=pick([2], "NOV. 22, 1934"),
                title=pick([3], "TECHWOOD PROJECT NO. 1101"),
            )
        )
    )

    fields = reader(client)(LINES)

    assert fields["drawing_number"].value == "A-19"
    assert fields["drawing_number"].line_ids == (1,)
    assert fields["date"].value == "1934-11-22"
    assert fields["title"].source == "llm:test-model"
    assert set(fields) == {"drawing_number", "date", "title"}


def test_values_not_on_the_cited_lines_are_rejected_and_recorded():
    client = FakeChat(json.dumps(answer(drawing_number=pick([1], "A-91"), scale=pick([7], "AS NOTED"))))
    llm = reader(client)

    fields = llm(LINES)

    assert fields == {}
    assert llm.usage.rejected == [("sheet1", "drawing_number", "A-91"), ("sheet1", "scale", "AS NOTED")]


def test_responses_are_cached_per_sheet(tmp_path):
    client = FakeChat(json.dumps(answer(drawing_number=pick([1], "A-19"))))

    first = reader(client, cache=tmp_path)(LINES)
    second = reader(client, cache=tmp_path)(LINES)

    assert first == second
    assert len(client.requests) == 1
    assert json.loads((tmp_path / "sheet1.json").read_text())["drawing_number"]["text"] == "A-19"


def test_malformed_responses_yield_no_fields():
    assert reader(FakeChat("not json"))(LINES) == {}
    assert reader(FakeChat(json.dumps({"drawing_number": "A-19"})))(LINES) == {}


def test_request_shape_and_usage_accounting():
    client = FakeChat(json.dumps(answer()))
    llm = LlmReader(client, "m", fields=FIELD_GUIDE, coerce=coerce, temperature=0.0)

    llm(LINES)

    [request] = client.requests
    assert request["temperature"] == 0.0
    assert request["response_format"]["type"] == "json_schema"
    assert "<ocr_lines>" in request["messages"][1]["content"]
    assert (llm.usage.calls, llm.usage.prompt_tokens, llm.usage.completion_tokens) == (1, 100, 20)


def test_prompt_marks_ocr_text_as_data_and_lists_positions():
    assert "not instructions" in instructions(FIELD_GUIDE)
    text = listing(LINES)
    assert text.splitlines()[2] == "[1] (0%, 43%, 30) A-19"
    assert listing([]) == "<ocr_lines>\n</ocr_lines>"


def test_grounding_ignores_spacing_and_case_but_not_content():
    assert grounded("nov 22 1934", LINES, [2])
    assert not grounded("NOV 23 1934", LINES, [2])
    assert not grounded("...", LINES, [2])
