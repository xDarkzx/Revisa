# Architecture decision records

Each significant decision is recorded once, with the context at the time and its
consequences, so a reviewer can see why the system looks the way it does. Records are never
edited after acceptance; a changed decision gets a new record that supersedes the old one.

| # | Decision | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-public-domain-evaluation-data.md) | Evaluate on public-domain historic construction drawings | Accepted |
| [0003](0003-ocr-first-grounded-extraction.md) | OCR first; the language model selects from OCR lines | Accepted |
| [0004](0004-locate-title-block-by-keywords.md) | Locate the title block from OCR keywords, not a vision model | Accepted |
| [0005](0005-keyless-azure-access.md) | Keyless access to Azure services | Accepted |
| [0006](0006-local-first-single-azure-proof.md) | Develop locally; deploy to Azure once as proof | Accepted |
| [0007](0007-two-readers-and-review-routing.md) | Two readers, word-level grounding, and routing to review | Accepted |
| [0008](0008-held-out-evaluation.md) | Develop on half the labelled sheets, report on the other half | Accepted |
