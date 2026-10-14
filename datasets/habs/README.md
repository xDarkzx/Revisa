# HABS/HAER drawing sheets: evaluation set

200 photographed drawing sheets, one from each of 200 building and engineering records of the
Historic American Buildings Survey and Historic American Engineering Record, sampled from
Wikimedia Commons ([ADR 0002](../../docs/adr/0002-public-domain-evaluation-data.md)). All are
public domain. The sheets range from an 1843 deed plan to 1990s highway drawings, and include
handwritten, faded, negative, rotated and damaged title blocks, plus some sheets that aren't
drawings at all (photographs, book pages). That mix is deliberate: a document pipeline in
production meets all of it.

| File | Contents |
|---|---|
| `manifest.jsonl` | One sheet per line: id, Commons title and URL, size, SHA-1, licence, Library of Congress record |
| `labels.jsonl` | Ground truth for every sheet, written from the sheet image |

`uv run revisa dataset-download` fetches the images (3000 px wide) into `data/sheets/`.

## Label format

```json
{"id": "0069f716df8f", "title_block": true,
 "drawing_number": ["A-19"], "title": ["TECHWOOD PROJECT NO. 1101"], "date": ["1934-11-22"],
 "scale": ["1/16\"=1'-0\""], "sheet_number": null, "sheet_count": null, "revision": null,
 "illegible": [], "note": "Revision table empty. 'GROUP 105' is a building group, not a sheet index."}
```

- Each field is a **list of acceptable readings**, or `null` when the sheet doesn't show one. A
  sheet with a printed drawing number and a handwritten filing number lists both, because
  either is a correct reading of the sheet.
- `illegible` names fields that are printed but can't be read by a person from the image. They
  are not scored either way.
- `note` records judgement calls so a reviewer can disagree with them specifically.

## Labelling rules

1. **Label what is printed on the drawing**, not the archive's caption. HABS/HAER stamps
   ("HABS No. GA-2257-5-17"), microfilm stamps ("JUN 20 1968 EAM") and later index numbers are
   never values.
2. `title_block` is true when the sheet has an identifying block or lettered title area, formal
   or not. Pictures, photographs and printed book pages are false.
3. `drawing_number`: the sheet's own identifier (drawing, plan, sheet or file number, or a
   handwritten filing number). Not project, contract, job, specification or order numbers.
4. `title`: the block's description of the drawing. Usually two readings: the full lettering
   and its core (`["PLAN OF STABLE, U.S. NAVY YARD MARE ISLAND", "PLAN OF STABLE"]`). Scored by
   word overlap (Jaccard at least 0.5) because a title's extent is a judgement call.
5. `date`: the date the drawing was made, drawn, submitted or approved, in ISO 8601 to the
   precision printed (`1900-05` for "May 1900"). Not revision, "as built", record, print or
   archive dates. Where only approval dates exist, the earliest is listed; alternatives are
   listed when two dates are equally the drawing's date. When the only date on the sheet marks
   a reissue of the whole drawing ("1932 Revision", "brought up to date 8-13-56"), that date is
   the drawing's date.
6. `scale`: as printed. Scales written only under individual views are not the sheet's scale.
7. `sheet_number`, `sheet_count`: from "sheet n of m" or "sheet no. n".
8. `revision`: the latest mark in a revision table. Revisions noted without a mark ("Revised
   6/18/02") have no revision value.

## How the labels were made and checked

Each sheet was transcribed with an AI assistant (Claude) from the image at full resolution,
zoomed into the title block, **independently of Revisa's OCR and extraction output**.

**Audit.** 20 sheets drawn at random from the test half (seed `20261014`) were read a second
time, blind to the existing labels, and the two readings compared field by field. They agreed
on 130 of 140 field values (93%). Each of the 10 disagreements was settled from the sheet
under magnification:

| Outcome | Fields | Sheets |
|---|---|---|
| Label wrong, corrected | 4 | 6b53358c7db8 date, 8c088e6a988f drawing number, b4845dc675e8 date, f51d8eac56cf scale |
| Second reading wrong, label kept | 4 | c480ae912b08 date, ef42a9186614 drawing number and date, 6b0d599835c7 revision |
| Rule unclear, rule 5 clarified, labels kept | 2 | b06b11a28713 date, 8c494b542a76 date |

So about 3% of label values were wrong before the audit, all of them single faint characters
(a digit or a month), not misread fields. Results were re-scored after the corrections; two
date scores rose by one or two points and nothing else changed.

- Hard sheets (faint handwriting, small print) carry most of the remaining uncertainty; those
  values are marked in `note` ("read from handwriting", "partly legible").
- A labelling error can count a correct extraction as wrong, or the reverse. The
  `extraction_error` issue template exists for reporting either.

Any change to a label must be a correction to match the sheet, never to match model output,
and is recorded below with its reason.

## Development and test halves

`revisa.evaluate.split_of` assigns each sheet to `dev` (93 sheets) or `test` (107 sheets) by a
hash of its id. Rules and prompts are developed against `dev`; results are reported on `test`.
One early diagnostic listed drawing-number misses across all 200 sheets before the split
existed; the rule changes after it are listed in the changelog so the test numbers can be weighed
accordingly.

## Change log

| Date | Sheet | Field | Change | Reason |
|---|---|---|---|---|
| 2026-10-14 | all | all | Initial labels | |
| 2026-10-14 | 6b53358c7db8 | date | 1931-05-18 to 1931-03-18 | Audit: block reads MAR-18-31 |
| 2026-10-14 | 8c088e6a988f | drawing_number | X3216 to X3218, X3216 | Audit: last digit blurred, 8 likelier |
| 2026-10-14 | b4845dc675e8 | date | 1960-02-01 to 1960-03-01 | Audit: approval date reads 3/1/60 |
| 2026-10-14 | f51d8eac56cf | scale | 1/2" to 1/4" (first of two scales) | Audit: fraction matches the 3/4 below |
