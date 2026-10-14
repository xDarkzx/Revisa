# 0007. Two readers, word-level grounding, and routing to review

- Status: Accepted
- Date: 2026-10-14

## Context

ADR 0003 has a language model choose OCR lines rather than read pixels. Testing that on real
sheets showed three things:

- Models cite the right lines but copy values loosely: several lines joined with newlines, the
  label included ("DWG. NO. A-19"), spacing changed. Requiring the value to be an exact
  substring of the cited lines rejected most correct answers.
- Deterministic rules (label, then the value beside or below it) are free and explainable, but
  on these drawings they read only a minority of fields: labels are misread by OCR ("N2" for
  "NO.") and many sheets have no labels at all.
- Neither reader is reliable alone, and the cost of an error depends entirely on whether a
  person sees it.

## Decision

1. **Grounding is checked word by word.** A model's value is kept only if every word and number
   in it appears in the lines it cited, ignoring case, spacing and punctuation. Values that fail
   are dropped and counted in the run's results (`ungrounded_values_rejected`).
2. **Values are coerced by the pack**, not by the model: dates are parsed to ISO 8601 from the
   copied text, labels are stripped, sheet numbers must be numbers. A value the pack can't
   coerce is rejected the same way.
3. **The model and the rules both read every sheet.** Where both give a value and they differ,
   the model's value is kept and the sheet goes to review with both shown. Where only one gives
   a value, it's used.
4. **Every sheet is routed.** A sheet is accepted only when it has a title block, every required
   field (drawing number, title, date), OCR confidence of at least 0.8 behind every value, and no
   disagreement between readers. Otherwise it goes to `needs_review` with each reason listed.

## Consequences

- A model can't add text to a drawing; the worst it can do is choose the wrong text, which the
  eval and the review queue both expose.
- Routing quality is measured directly: of the sheets with any error, the share sent to review,
  and of the sheets accepted, the share with an error (the silent error rate).
- The rules cost nothing per sheet, so cross-checking is free.
- Disagreements between a strong model and weak rules send some correct sheets to review. That
  is the intended trade: review time for fewer silent errors.
