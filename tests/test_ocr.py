import pytest
from PIL import Image

from revisa.ocr import AzureReadEngine, Box, Line, lines_from_analyze_result, lines_from_json, lines_to_json

ANALYZE_RESULT = {
    "pages": [
        {
            "unit": "pixel",
            "words": [
                {"content": "SHEET", "confidence": 0.99, "span": {"offset": 0, "length": 5}},
                {"content": "A-19", "confidence": 0.71, "span": {"offset": 6, "length": 4}},
            ],
            "lines": [
                {
                    "content": "SHEET A-19",
                    "polygon": [100, 50, 220, 52, 220, 80, 100, 78],
                    "spans": [{"offset": 0, "length": 10}],
                }
            ],
        }
    ]
}


def test_document_intelligence_lines_use_weakest_word_confidence():
    [line] = lines_from_analyze_result(ANALYZE_RESULT)

    assert line.text == "SHEET A-19"
    assert line.box == Box(100, 50, 220, 80)
    assert line.confidence == 0.71


def test_non_pixel_units_are_rejected():
    with pytest.raises(ValueError, match="pixel"):
        lines_from_analyze_result({"pages": [{"unit": "inch", "lines": []}]})


class FakeClient:
    def __init__(self):
        self.calls = []

    def begin_analyze_document(self, model_id, body, content_type):
        self.calls.append((model_id, content_type, body.read()[:8]))
        return type(
            "Poller", (), {"result": lambda _self: type("R", (), {"as_dict": lambda _s: ANALYZE_RESULT})()}
        )()


def test_azure_engine_sends_jpeg_to_prebuilt_read():
    client = FakeClient()

    lines = AzureReadEngine("https://unused", client=client).read(Image.new("L", (10, 10)))

    [(model, content_type, head)] = client.calls
    assert (model, content_type) == ("prebuilt-read", "application/octet-stream")
    assert head.startswith(b"\xff\xd8")  # JPEG, to stay under the free tier's 4 MB limit
    assert lines[0].text == "SHEET A-19"


def test_box_geometry():
    a, b = Box(0, 0, 10, 10), Box(13, 14, 20, 20)
    assert a.gap_to(b) == 5.0
    assert a.gap_to(Box(5, 5, 6, 6)) == 0.0
    assert a.union(b) == Box(0, 0, 20, 20)
    assert a.padded(5, 12, 100) == Box(0, 0, 12, 15)


def test_json_round_trip():
    lines = [Line("DATE", Box(1, 2, 3, 4), 0.5)]
    assert lines_from_json(lines_to_json(lines)) == lines
