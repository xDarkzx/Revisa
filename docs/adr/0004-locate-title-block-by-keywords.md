# 0004. Locate the title block from OCR keywords, not a vision model

- Status: Accepted
- Date: 2026-10-14

## Context

OCR of a crop around the title block reads far more small text than OCR of the whole page.
Asking a local vision model for the title block's bounding box failed on all three test sheets:
it said a clear title block didn't exist and returned coordinates in mixed units.

## Decision

Run OCR on the whole page, find lines containing title-block vocabulary (DRAWN, CHECKED,
SCALE, SHEET, DATE, REVISIONS, APPROVED, ...), grow a region around them to neighbouring
text, and crop that region at full resolution for a second OCR pass. No keyword hits means no
title block.

## Consequences

- Deterministic, fast, free, and explainable ("these five words put the crop here").
- Sheets with unusual vocabulary or very poor scans may be missed; they surface as "no title
  block found" and go to review, and the eval counts them.
- The keyword list is pack configuration, so other document types supply their own anchors.
