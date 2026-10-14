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
   listed when two dates are equally the drawing's date.
6. `scale`: as printed. Scales written only under individual views are not the sheet's scale.
7. `sheet_number`, `sheet_count`: from "sheet n of m" or "sheet no. n".
8. `revision`: the latest mark in a revision table. Revisions noted without a mark ("Revised
   6/18/02") have no revision value.

## Who labelled it, and how to weigh that

The labels were transcribed by an AI assistant (Claude) reading each sheet image at full
resolution, zoomed into the title block, **independently of Revisa's OCR and extraction output**.
They have not yet been verified by a second person. Known consequences:

- Hard sheets (faint handwriting, small print) carry most of the label uncertainty; those
  values are marked in `note` ("read from handwriting", "partly legible").
- A labeller error can count a correct extraction as wrong, or the reverse. The
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
