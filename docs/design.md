# Revisa: design

## Problem

On a construction project, drawings arrive in batches of tens to hundreds of sheets, each
revised many times. A document controller opens every sheet, reads the **title block** (drawing
number, title, revision, date, sheet n of m, scale), types it into the **drawing register**, and
works out what superseded what. Mistakes here mean people build from superseded drawings.

Revisa reads the title blocks, keeps the register, catches inconsistencies across a set, and
sends anything it is unsure about to a person, with the reasons and the evidence.

## Principles

1. **Every value is grounded.** An extracted value carries the OCR lines it came from. A model
   can only choose among OCR lines, and its value is rejected unless every word of it is on the
   lines it cited ([ADR 0003](adr/0003-ocr-first-grounded-extraction.md),
   [ADR 0007](adr/0007-two-readers-and-review-routing.md)).
2. **Uncertainty goes to a person.** Each sheet is `accepted` or `needs_review`, with reasons.
   The headline metric isn't only accuracy: it's how many wrong sheets review catches and how
   many slip through, because a flagged error costs seconds and a silent one costs a rebuild.
3. **The register is the source of truth for questions.** "What's the current revision of
   A-19?" is answered by querying the register, not by retrieving text and guessing.
4. **Industry-specific parts are a pack.** The core (OCR, locating, grounding, routing, register,
   evaluation) knows nothing about construction. A pack supplies the field list and guide, the
   keywords that locate the block, the rules, value coercion and scoring. Construction is built;
   medical referrals and supplier invoices are specified in [packs.md](packs.md).

## Pipeline

```
sheet image
  │
  ├─ OCR the whole page ──────────────── RapidOCR (local) │ Document Intelligence prebuilt-read (Azure)
  ├─ locate the title block ──────────── keyword lines clustered and grown (ADR 0004)
  ├─ crop it, enlarge it, OCR again ──── small lettering the page pass missed
  │
  ├─ reader 1: pack rules ─────────────── label → value beside or below it; free, deterministic
  ├─ reader 2: language model ─────────── chooses OCR line ids per field (Ollama │ Azure OpenAI)
  ├─ grounding + coercion ─────────────── every word on the cited lines; dates to ISO 8601
  │
  ├─ route ────────────────────────────── accepted, or needs_review with reasons
  └─ register ─────────────────────────── SQLite │ Cosmos DB; set checks; CSV export
```

Each stage caches its output per sheet under `data/`, so a change to the readers re-scores in
seconds and a paid service is called once per sheet, ever.

### Routing rules

A sheet is accepted only if all of these hold; otherwise every failing condition is listed:

- a title block was found;
- drawing number, title and date were all read;
- every value's source lines have OCR confidence of at least 0.8;
- the two readers don't disagree on any field.

### Register checks

Across the sheets of one project: the same drawing number at the same revision twice
(duplicate); the same number at different revisions (the earlier ones are superseded); sheets
missing from a numbered set; sheets disagreeing about the set size.

## Data and evaluation

200 public-domain photographed drawings, one per building record
([datasets/habs](../datasets/habs/README.md)), each labelled field by field with every
acceptable reading. Scoring per field distinguishes correct, missed, wrong, and invented values,
and per sheet measures full correctness and routing. Rules and prompts are developed on 93
sheets and reported on the other 107 ([ADR 0008](adr/0008-held-out-evaluation.md)).

## Profiles

| | Local | Azure |
|---|---|---|
| OCR | RapidOCR (ONNX, CPU) | Document Intelligence `prebuilt-read`, F0 |
| Model | Ollama (`qwen2.5-coder:14b` by default) | Azure OpenAI `gpt-4.1-mini`, GlobalStandard |
| Register | SQLite | Cosmos DB for NoSQL, free tier, partition `/project` |
| Auth | none needed | Entra ID only; key auth disabled on every service ([ADR 0005](adr/0005-keyless-azure-access.md)) |

The profile is chosen explicitly per command (`--engine`, `--llm`, `--store`); nothing falls
back silently from one to the other.

## Deployment

`infra/main.bicep` declares exactly what the code uses: Document Intelligence, an AI Services
account with the model deployment, Cosmos DB with its database and container, and data-plane
role assignments for the identities given. `scripts/azure-proof.sh` deploys it, runs the full
evaluation and register load once, records the evidence in [azure-proof](azure-proof/), and
deletes the resource group ([ADR 0006](adr/0006-local-first-single-azure-proof.md)).

## Not built yet

These are designed for but not implemented; each would be its own pull request and ADR.

- **Intake.** Sheets arrive by upload to Blob Storage; an event queues them and a Container Apps
  job (KEDA, scale to zero) processes the queue. Today the pipeline runs as a batch CLI.
- **Review UI.** A page showing the sheet with the evidence lines highlighted and the reasons,
  where a person confirms or corrects values; corrections become new labelled data.
- **Questions in natural language** over the register, answered by an agent whose only tool is
  the register query API.
- CAD/DWG input, comparing drawing content between revisions, SharePoint intake, multi-tenancy.
