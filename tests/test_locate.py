import re

from revisa.locate import LocateConfig, locate
from revisa.ocr import Box, Line
from revisa.packs.construction import ARCHIVE_STAMP, TITLE_BLOCK_KEYWORDS

CONFIG = LocateConfig(keywords=TITLE_BLOCK_KEYWORDS, ignore=ARCHIVE_STAMP)
W, H = 4000, 3000


def line(text, x, y, w=300, h=30):
    return Line(text, Box(x, y, x + w, y + h), 0.9)


TITLE_BLOCK = [
    line("TECHWOOD PROJECT NO. 1101", 3200, 2500),
    line("DRAWN BY LWW", 3200, 2560),
    line("CHECKED BY GB", 3200, 2600),
    line("DATE NOV. 22 1934", 3200, 2640),
    line("BURGE AND STEVENS", 3550, 2560),
]
DRAWING_BODY = [line("FIRST FLOOR PLAN", 500, 800), line("KITCHEN", 900, 1200)]


def test_finds_the_dense_cluster_and_grows_to_neighbouring_text():
    region = locate(TITLE_BLOCK + DRAWING_BODY, W, H, CONFIG)

    assert region is not None
    assert {ln.text for ln in region.lines} == {ln.text for ln in TITLE_BLOCK}
    assert region.box.x0 < 3200
    assert region.box.x1 > 3850


def test_archive_stamp_is_never_part_of_the_block():
    stamp = line("HAB5N0.6A-2257-J-17", 3300, 2700)

    region = locate([*TITLE_BLOCK, stamp], W, H, CONFIG)

    assert stamp not in region.lines


def test_no_keywords_means_no_title_block():
    assert locate(DRAWING_BODY, W, H, CONFIG) is None


def test_lone_keyword_far_from_dense_cluster_loses():
    stray = line("SCALE 1/8 INCH", 400, 300)

    region = locate([*TITLE_BLOCK, stray], W, H, CONFIG)

    assert stray not in region.lines


def test_region_covering_most_of_the_page_is_rejected():
    grid = [line("SHEET", x, y, w=380, h=280) for x in range(0, W, 400) for y in range(0, H, 300)]
    assert locate(grid, W, H, CONFIG) is None


def test_keyword_match_needs_a_word_start():
    assert TITLE_BLOCK_KEYWORDS.search("UPDATE FLOOR PLAN") is None
    assert TITLE_BLOCK_KEYWORDS.search("DATENOV.22") is not None
    assert ARCHIVE_STAMP.search("HAB5N0.6A-2257") is not None
    assert ARCHIVE_STAMP.search("PHASE 2") is None


def test_ignore_pattern_is_configurable():
    config = LocateConfig(keywords=re.compile("TOTAL"), ignore=re.compile("^$"))
    assert locate([line("TOTAL", 10, 10)], W, H, config) is not None
