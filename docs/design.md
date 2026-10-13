# Revisa: design

## Problem

On a construction project, drawings arrive in batches of tens to hundreds of sheets, each
revised many times. A document controller opens every sheet, reads the **title block** (drawing
number, title, revision, date, sheet n of m, who drew and checked it), types it into the
**drawing register**, and works out what superseded what. Mistakes here mean people build from
superseded drawings.

Revisa reads the title blocks, keeps the register, catches inconsistencies, and sends anything
it is unsure about to a person, with the evidence highlighted.

## Principles

1. **Every value is grounded.** An extracted field must be traceable to text read from the sheet
   (Document Intelligence OCR) inside the title-block region. A value the model "read" that the
   OCR never saw is not trusted, whatever the model's stated confidence.
2. **Uncertainty goes to a person.** Each sheet is `accepted` or `needs_review`. The headline
   metric isn't only accuracy: it's **how many wrong extractions were caught by review**, because
   an error that's flagged costs seconds and an error that isn't costs a rebuild.
3. **The register is the source of truth for questions.** The agent answers "what's the latest
   revision of S-104?" by querying the register, not by retrieving text and guessing.
4. **Industry-specific parts are a pack.** The core (intake, extraction, grounding, review,
   register, agent) knows nothing about construction. A pack supplies the schema, extraction
   instructions, validation rules and eval set. Construction is implemented; medical referrals
   and supplier invoices are specified in `packs/README.md` to show the boundary holds.

## Pipeline

```
upload ─► Blob "inbox" ─► Event Grid ─► Storage queue ─► processor job (Container Apps, KEDA)
                                                            │
             Document Intelligence (layout: words + boxes) ─┤
             locate title block, crop                       │
             Foundry vision model ─► structured fields ─────┤
             grounding check against OCR words              │
             pack rules (sequence, revision order, dupes) ──┤
                                                            ▼
                                     register (Cosmos DB) ─► review UI / API / agent / CSV export
```

## Data

Real construction drawings in the public domain: Historic American Buildings Survey photographs
of original architectural drawings (e.g. 1904-1988 US Navy sheets), hosted on Wikimedia
Commons. About 970 sheets across building records of 4-20 sheets each, with real revision tables
and handwritten title blocks. The repo commits a manifest (source URL, licence, checksum) and the
labels; a script downloads the images.

**Ground truth.** Labels are drafted by a model, then each one is checked and corrected by a person
in the review UI, which records who verified it and when. Unverified labels are never scored.

## Evaluation

Per field: exact match after normalisation (case, whitespace, revision-letter forms). Per
sheet: all required fields correct. Review routing: of the wrong extractions, the share sent to
`needs_review` (recall), and of the sheets sent to review, the share that were actually wrong
(precision). Plus cost per sheet and latency. Results are committed per run.

## Profiles

`azure`: Document Intelligence + Azure OpenAI vision + Cosmos DB + Blob, keyless via managed
identity. `local`: Ollama vision model (`qwen2.5vl:7b`), no OCR grounding available, SQLite
register. The profile is an explicit setting; nothing falls back silently.

## Out of scope (v1)

CAD/DWG files, comparing drawing contents between revisions (geometry diffing), SharePoint and
Power Automate intake (documented as the client-facing adapter; needs a Microsoft 365 tenant),
multi-tenant.
