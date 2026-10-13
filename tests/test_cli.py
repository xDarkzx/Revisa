import json

from PIL import Image

from revisa import cli, dataset, ocr
from revisa.ocr import Box, Line
from tests.test_dataset import sheet


class FakeEngine:
    name = "fake"
    calls = 0

    def read(self, image):
        FakeEngine.calls += 1
        return [Line("SHEET A-19", Box(1, 2, 3, 4), 0.9)]


def test_ocr_pages_caches_each_sheet_once(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "RapidOcrEngine", FakeEngine)
    manifest = tmp_path / "m.jsonl"
    dataset.write_manifest([sheet("a", 1)], manifest)
    Image.new("RGB", (10, 10)).save(tmp_path / "a-1.jpg")
    args = [
        "ocr-pages",
        "--manifest",
        str(manifest),
        "--sheets",
        str(tmp_path),
        "--out",
        str(tmp_path / "ocr"),
    ]

    cli.main(args)
    cli.main(args)

    assert FakeEngine.calls == 1
    cached = json.loads((tmp_path / "ocr" / "a-1.json").read_text())
    assert cached[0]["text"] == "SHEET A-19"


def test_dataset_commands_write_manifest_and_download(tmp_path, monkeypatch, capsys):
    sheets = [sheet("a", 1), sheet("b", 1)]
    monkeypatch.setattr(dataset, "CommonsClient", lambda: None)
    monkeypatch.setattr(dataset, "collect_sheets", lambda client: sheets)
    monkeypatch.setattr(dataset, "download_sheets", lambda client, s, dest, width: [dest / x.id for x in s])
    manifest = tmp_path / "m.jsonl"

    cli.main(["dataset-collect", "--total", "2", "--out", str(manifest)])
    cli.main(["dataset-download", "--manifest", str(manifest), "--dest", str(tmp_path)])

    assert dataset.read_manifest(manifest) == sheets
    out = capsys.readouterr().out
    assert "wrote 2 from 2 records" in out
    assert "2 sheets in" in out
