# 0002. Evaluate on public-domain historic construction drawings

- Status: Accepted
- Date: 2026-10-14

## Context

Extraction accuracy only means something if it's measured on real drawings with real title
blocks. Current commercial drawing sets are copyrighted and rarely published. Synthetic
drawings would test the generator, not the reader.

## Decision

Use Historic American Buildings Survey photographs of original architectural and engineering
drawings (1840s-1990s), hosted on Wikimedia Commons with a public-domain licence and a Library
of Congress record per file. Collect every candidate (1,406 sheets) and sample 200 from 200
different building records, so no single drawing office or era dominates. Commit the manifest
(provenance, licence, checksum) and the labels; download images by script.

## Consequences

- The data is legally clean and anyone can rebuild the exact dataset.
- It's harder than modern CAD output: handwriting, rotated title blocks, stains, and HABS
  archive stamps that look like drawing numbers but aren't. Scores are conservative for modern
  drawings.
- Some sheets have no title block at all. The correct output there is "needs review", which
  the evaluation rewards.
- Old drawings lack some modern conventions (discipline prefixes, revision clouds), so those
  features are tested less.
