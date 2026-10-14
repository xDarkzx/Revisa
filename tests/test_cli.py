import json

from PIL import Image

from revisa import cli, dataset, runs
from revisa.ocr import Box, Line
from tests.test_dataset import sheet


class FakeEngine:
    name = "fake"
    calls = 0

    def read(self, image):
        FakeEngine.calls += 1
        return [Line("DRAWN BY LWW", Box(1, 2, 8, 4), 0.9), Line("DATE NOV 22 1934", Box(1, 5, 8, 7), 0.9)]


def _sheets(tmp_path, monkeypatch):
    FakeEngine.calls = 0
    monkeypatch.setattr(runs, "RapidOcrEngine", FakeEngine)
    monkeypatch.setattr(cli, "SHEETS", tmp_path / "sheets")
    monkeypatch.setattr(cli, "OCR_ROOT", tmp_path / "ocr")
    (tmp_path / "sheets").mkdir()
    Image.new("RGB", (10, 10)).save(tmp_path / "sheets" / "a-1.jpg")
    manifest = tmp_path / "m.jsonl"
    dataset.write_manifest([sheet("a", 1)], manifest)
    return manifest


def test_ocr_commands_cache_each_sheet_once(tmp_path, monkeypatch):
    manifest = _sheets(tmp_path, monkeypatch)

    for _ in range(2):
        cli.main(["ocr-pages", "--manifest", str(manifest)])
        cli.main(["ocr-blocks", "--manifest", str(manifest)])

    assert FakeEngine.calls == 2  # one page read, one block read
    page = json.loads((tmp_path / "ocr" / "rapidocr" / "pages" / "a-1.json").read_text())
    block = json.loads((tmp_path / "ocr" / "rapidocr" / "blocks" / "a-1.json").read_text())
    assert page[1]["text"] == "DATE NOV 22 1934"
    assert block["box"] is not None


def test_run_scores_and_report_renders(tmp_path, monkeypatch, capsys):
    manifest = _sheets(tmp_path, monkeypatch)
    cli.main(["ocr-pages", "--manifest", str(manifest)])
    cli.main(["ocr-blocks", "--manifest", str(manifest)])
    labels = tmp_path / "labels.jsonl"
    labels.write_text(
        json.dumps(
            {
                "id": "a-1",
                "title_block": True,
                "drawing_number": None,
                "title": None,
                "date": ["1934-11-22"],
                "scale": None,
                "sheet_number": None,
                "sheet_count": None,
                "revision": None,
                "illegible": [],
                "note": "",
            }
        )
        + "\n"
    )

    cli.main(["run", "t", "--labels", str(labels), "--out", str(tmp_path / "results")])
    cli.main(["report", str(tmp_path / "results" / "t.json"), "--split", "all"])

    result = json.loads((tmp_path / "results" / "t.json").read_text())
    assert result["summary"]["all"]["fields"]["date"]["counts"] == {"correct": 1}
    assert result["per_sheet"][0]["values"]["date"] == "1934-11-22"
    assert "| t | rapidocr | rules |" in capsys.readouterr().out


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
