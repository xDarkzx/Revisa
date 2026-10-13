from PIL import Image

from revisa.blocks import BlockRead, block_from_json, block_to_json, read_block, reading_order
from revisa.ocr import Box, Line
from revisa.packs.construction import LOCATE


def line(text, x, y, w=100, h=20):
    return Line(text, Box(x, y, x + w, y + h), 0.9)


class FakeEngine:
    name = "fake"

    def __init__(self):
        self.sizes = []

    def read(self, image):
        self.sizes.append(image.size)
        return [line("SHEET A-19", 10, 10), line("HABS GA-2257", 10, 40)]


def test_crop_is_enlarged_and_lines_are_mapped_back_to_page_pixels():
    page = [line("DRAWN BY LWW", 3000, 2500), line("DATE NOV 22 1934", 3000, 2540)]
    engine = FakeEngine()

    block = read_block(Image.new("RGB", (4000, 3000)), page, engine, LOCATE)

    assert block is not None
    width, _ = engine.sizes[0]
    assert width >= 1600 or width / (block.box.x1 - block.box.x0) >= 2.9
    [read] = block.lines  # the archive stamp is dropped
    assert read.text == "SHEET A-19"
    assert block.box.x0 <= read.box.x0 < block.box.x1
    assert block.box.y0 <= read.box.y0 < block.box.y1
    assert set(block.anchors) == {"DRAWN BY LWW", "DATE NOV 22 1934"}


def test_no_keywords_means_no_block():
    assert read_block(Image.new("RGB", (100, 100)), [line("KITCHEN", 1, 1)], FakeEngine(), LOCATE) is None


def test_reading_order_groups_rows_then_sorts_left_to_right():
    lines = [line("B", 300, 102), line("A", 10, 100), line("C", 10, 200)]

    assert [ln.text for ln in reading_order(lines)] == ["A", "B", "C"]
    assert reading_order([]) == []


def test_json_round_trip():
    block = BlockRead(box=Box(1, 2, 3, 4), anchors=("DATE",), lines=(line("DATE", 1, 2),))

    assert block_from_json(block_to_json(block)) == block
    assert block_from_json(block_to_json(None)) is None
