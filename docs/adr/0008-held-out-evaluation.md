# 0008. Develop on half the labelled sheets, report on the other half

- Status: Accepted
- Date: 2026-10-14

## Context

Rules and prompts were tuned by looking at the sheets they got wrong. Scoring them on those same
sheets overstates how well they'll do on drawings nobody has looked at. With 200 labelled
sheets, a held-out half is still big enough to report on.

## Decision

`revisa.evaluate.split_of` assigns each sheet to `dev` or `test` by a SHA-256 hash of its id (93
and 107 sheets). Rule and prompt development uses `dev` only. Every run is scored on both halves
and the README reports `test`. Each sheet comes from a different building record, so the halves
share no drawing sets.

## Consequences

- The reported numbers are a fair estimate for unseen sheets of this kind, within the error bars
  of about 100 sheets (roughly plus or minus 10 points on a proportion).
- Before the split existed, one diagnostic listed drawing-number misses across all 200 sheets
  and informed two rule changes (looser "NO." matching and unlabelled identifiers). This is
  disclosed in `datasets/habs/README.md`; the effect on the test numbers is limited to the
  drawing-number field.
- The split is fixed by the hash, so adding sheets never moves an existing one between halves.
