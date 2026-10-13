"""Build the evaluation dataset from public-domain drawings on Wikimedia Commons.

The sheets are Historic American Buildings Survey photographs of original architectural and
engineering drawings. The manifest records, for every sheet, where it came from and under what
licence, so the dataset can be rebuilt exactly and its provenance checked.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
# Wikimedia asks API clients to identify themselves with a contact address.
USER_AGENT = "RevisaDataset/0.1 (https://github.com/xDarkzx/Revisa; dkstudiosnz@gmail.com)"
SEARCH_QUERIES = (
    'intitle:"photocopy of drawing"',
    'intitle:"photocopy of original drawing"',
    'intitle:"copy of drawing"',
)
ACCEPTED_LICENCES = {"Public domain"}
IMAGE_MIMES = {"image/tiff", "image/jpeg", "image/png"}
INFO_BATCH = 50  # imageinfo titles per request; the API maximum for anonymous clients
_LOC_ITEM = re.compile(r"loc\.gov/pictures/item/([a-z]{2}\d+)", re.IGNORECASE)


class Sheet(BaseModel):
    """One drawing sheet: an image file on Commons plus its provenance."""

    id: str  # stable short id derived from the Commons title
    commons_title: str
    page_url: str
    file_url: str
    width: int
    height: int
    mime: str
    sha1: str  # of the original file, as reported by Commons
    licence: str
    source_url: str  # Library of Congress record
    record: str  # Library of Congress HABS/HAER record, e.g. "ca1601"; sheets in one set share it


class DatasetError(RuntimeError):
    pass


def sheet_id(commons_title: str) -> str:
    return hashlib.sha1(commons_title.encode(), usedforsecurity=False).hexdigest()[:12]


class CommonsClient:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(timeout=30.0)
        self._http.headers["User-Agent"] = USER_AGENT

    def search_titles(self, query: str) -> Iterator[str]:
        params: dict[str, str | int] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": 6,
            "srlimit": 500,
            "format": "json",
        }
        while True:
            data = self._get(params)
            for hit in data["query"]["search"]:
                yield str(hit["title"])
            if "continue" not in data:
                return
            params.update(data["continue"])

    def image_info(self, titles: list[str], thumb_width: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "action": "query",
            "titles": "|".join(titles),
            "prop": "imageinfo",
            "iiprop": "url|size|sha1|mime|extmetadata",
            "iiextmetadatafilter": "LicenseShortName|Credit",
            "format": "json",
        }
        if thumb_width:
            params["iiurlwidth"] = thumb_width
        pages = self._get(params)["query"]["pages"].values()
        return [p for p in pages if "imageinfo" in p]

    def download(self, url: str, dest: Path) -> None:
        with self._http.stream("GET", url) as response:
            if response.is_error:
                raise DatasetError(f"GET {url} -> {response.status_code}")
            with dest.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)

    def _get(self, params: dict[str, str | int]) -> dict[str, Any]:
        # POST because batches of ~250-character file titles exceed URL length limits.
        # maxlag asks Commons to refuse the request rather than add load when replicas lag.
        response = self._http.post(COMMONS_API, data={**params, "maxlag": 5})
        if response.is_error:
            raise DatasetError(f"Commons API -> {response.status_code}: {response.text[:200]}")
        data: dict[str, Any] = response.json()
        if "error" in data:
            raise DatasetError(f"Commons API error: {data['error']}")
        return data


def to_sheet(page: dict[str, Any]) -> Sheet | None:
    """A Sheet for an accepted page, or None when it isn't a public-domain image."""
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    licence = _plain(meta.get("LicenseShortName", {}).get("value", ""))
    credit = _plain(meta.get("Credit", {}).get("value", ""))
    record = _LOC_ITEM.search(credit)
    if licence not in ACCEPTED_LICENCES or info.get("mime") not in IMAGE_MIMES or record is None:
        return None
    return Sheet(
        id=sheet_id(page["title"]),
        commons_title=page["title"],
        page_url=info["descriptionurl"],
        file_url=info["url"],
        width=info["width"],
        height=info["height"],
        mime=info["mime"],
        sha1=info["sha1"],
        licence=licence,
        source_url=f"https://www.loc.gov/pictures/item/{record.group(1)}",
        record=record.group(1).lower(),
    )


def collect_sheets(client: CommonsClient, queries: Iterable[str] = SEARCH_QUERIES) -> list[Sheet]:
    titles = sorted({t for q in queries for t in client.search_titles(q)})
    sheets = []
    for start in range(0, len(titles), INFO_BATCH):
        for page in client.image_info(titles[start : start + INFO_BATCH]):
            sheet = to_sheet(page)
            if sheet is not None:
                sheets.append(sheet)
    return sorted(sheets, key=lambda s: s.id)


def stratified_sample(sheets: list[Sheet], total: int, per_record: int, seed: int) -> list[Sheet]:
    """Spread the sample across many buildings instead of letting the biggest sets dominate.

    Takes up to ``per_record`` sheets from each record, visiting records round-robin in a seeded
    random order until ``total`` is reached.
    """
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not security
    by_record: dict[str, list[Sheet]] = defaultdict(list)
    for sheet in sheets:
        by_record[sheet.record].append(sheet)
    for group in by_record.values():
        rng.shuffle(group)
    records = sorted(by_record)
    rng.shuffle(records)

    chosen: list[Sheet] = []
    for round_ in range(per_record):
        for record in records:
            group = by_record[record]
            if round_ < len(group) and len(chosen) < total:
                chosen.append(group[round_])
    return sorted(chosen, key=lambda s: s.id)


def write_manifest(sheets: list[Sheet], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(s.model_dump_json() + "\n" for s in sheets), encoding="utf-8")


def read_manifest(path: Path) -> list[Sheet]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Sheet.model_validate(json.loads(line)) for line in lines if line.strip()]


def download_sheets(client: CommonsClient, sheets: list[Sheet], dest: Path, width: int) -> list[Path]:
    """Download a ``width``-pixel JPEG rendering of each sheet. Existing files are kept."""
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for start in range(0, len(sheets), INFO_BATCH):
        batch = sheets[start : start + INFO_BATCH]
        thumbs = {
            p["title"]: p["imageinfo"][0]["thumburl"]
            for p in client.image_info([s.commons_title for s in batch], thumb_width=width)
        }
        for sheet in batch:
            path = dest / f"{sheet.id}.jpg"
            if not path.exists():
                if sheet.commons_title not in thumbs:
                    raise DatasetError(f"Commons no longer serves {sheet.commons_title}")
                client.download(thumbs[sheet.commons_title], path)
            paths.append(path)
    return paths


def _plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()
