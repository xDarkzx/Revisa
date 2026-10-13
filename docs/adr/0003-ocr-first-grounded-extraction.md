# 0003. OCR first; the language model selects from OCR lines

- Status: Accepted
- Date: 2026-10-14

## Context

The obvious design is to give a vision model the title-block image and ask for the fields.
Tested on real sheets, local vision models (qwen2.5vl 7B, qwen3.5 9B) read text but assigned it
to the wrong fields, invented values, and took up to 92 s per sheet. Even strong models give no
evidence for where a value came from, so a wrong value looks exactly like a right one.

## Decision

Split reading from understanding. An OCR engine (RapidOCR locally, Azure Document Intelligence
`prebuilt-read` in Azure) reads every line with its position. A language model then assigns
fields by **choosing OCR line IDs**, and the value is taken from those lines. A value that
doesn't come from the OCR output can't be produced.

## Consequences

- Every extracted value is grounded by construction and can be highlighted on the sheet.
- The language model's job is easier (sorting text, not reading pixels), so small local models
  become usable and large ones cheaper.
- OCR misreads become extraction errors (e.g. `HAB5` for `HABS`). The review step and the eval
  measure this directly; the OCR engine is swappable without touching the rest.
- Handwritten values OCR can't read can't be extracted; those sheets go to review.
