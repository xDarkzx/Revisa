import httpx
import pytest
import respx

from revisa.dataset import (
    COMMONS_API,
    CommonsClient,
    DatasetError,
    Sheet,
    collect_sheets,
    read_manifest,
    sheet_id,
    stratified_sample,
    to_sheet,
    write_manifest,
)


def page(
    title,
    licence="Public domain",
    credit="https://www.loc.gov/pictures/item/ca1601.photos.019391p",
    mime="image/tiff",
):
    return {
        "title": title,
        "imageinfo": [
            {
                "url": f"https://upload.example/{title}",
                "descriptionurl": f"https://commons.example/{title}",
                "width": 5000,
                "height": 4000,
                "mime": mime,
                "sha1": "abc",
                "extmetadata": {
                    "LicenseShortName": {"value": licence},
                    "Credit": {"value": f"<a>{credit}</a>"},
                },
            }
        ],
    }


def test_public_domain_sheet_keeps_provenance():
    sheet = to_sheet(page("File:Photocopy of drawing A-31.tif"))

    assert sheet.record == "ca1601"
    assert sheet.source_url == "https://www.loc.gov/pictures/item/ca1601"
    assert sheet.id == sheet_id("File:Photocopy of drawing A-31.tif")


@pytest.mark.parametrize(
    "kwargs",
    [{"licence": "CC BY-SA 4.0"}, {"mime": "application/pdf"}, {"credit": "Own work"}],
    ids=["not-public-domain", "not-an-image", "no-library-of-congress-record"],
)
def test_other_files_are_rejected(kwargs):
    assert to_sheet(page("File:x.tif", **kwargs)) is None


def sheet(record, n):
    return Sheet(
        id=f"{record}-{n}",
        commons_title=f"File:{record}-{n}",
        page_url="p",
        file_url="f",
        width=1,
        height=1,
        mime="image/tiff",
        sha1="s",
        licence="Public domain",
        source_url="u",
        record=record,
    )


def test_sample_spreads_across_records_and_is_reproducible():
    sheets = [sheet("big", n) for n in range(20)] + [sheet(f"r{i}", 0) for i in range(5)]

    sample = stratified_sample(sheets, total=6, per_record=2, seed=1)

    assert len(sample) == 6
    assert sum(s.record == "big" for s in sample) <= 2
    assert sample == stratified_sample(sheets, total=6, per_record=2, seed=1)


def test_per_record_cap_wins_over_total():
    sheets = [sheet("big", n) for n in range(20)] + [sheet("small", 0)]

    assert len(stratified_sample(sheets, total=10, per_record=2, seed=1)) == 3


def test_manifest_round_trip(tmp_path):
    sheets = [sheet("a", 1), sheet("b", 2)]
    write_manifest(sheets, tmp_path / "m.jsonl")
    assert read_manifest(tmp_path / "m.jsonl") == sheets


@respx.mock
def test_collect_pages_through_search_and_filters():
    def api(request):
        params = dict(httpx.QueryParams(request.content.decode()))
        if params.get("list") == "search":
            if "sroffset" not in params:
                return httpx.Response(
                    200, json={"query": {"search": [{"title": "File:a.tif"}]}, "continue": {"sroffset": 1}}
                )
            return httpx.Response(200, json={"query": {"search": [{"title": "File:b.tif"}]}})
        pages = {"1": page("File:a.tif"), "2": page("File:b.tif", licence="CC BY 4.0")}
        return httpx.Response(200, json={"query": {"pages": pages}})

    respx.post(COMMONS_API).mock(side_effect=api)

    sheets = collect_sheets(CommonsClient(httpx.Client()), queries=["q"])

    assert [s.commons_title for s in sheets] == ["File:a.tif"]


@respx.mock
def test_api_errors_are_raised():
    respx.post(COMMONS_API).mock(return_value=httpx.Response(200, json={"error": {"code": "maxlag"}}))

    with pytest.raises(DatasetError, match="maxlag"):
        list(CommonsClient(httpx.Client()).search_titles("q"))
