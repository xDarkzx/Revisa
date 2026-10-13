# 0006. Develop locally; deploy to Azure once as proof

- Status: Accepted
- Date: 2026-10-14

## Context

The project runs on a free Azure trial. Iterating against cloud services spends credit on
every run, and the purpose of Azure here is to prove the system deploys and runs correctly,
not to host development.

## Decision

Every component has a local implementation behind the same interface as its Azure one:
RapidOCR for Document Intelligence, an Ollama model for Azure OpenAI, SQLite for Cosmos DB, the
filesystem for Blob Storage. The profile is an explicit setting and nothing falls back between
them silently. Azure is deployed once from Bicep, the full evaluation is run, the results are
committed, and the resource group is deleted.

## Consequences

- Development costs nothing and works offline.
- The interfaces must be honest abstractions; contract tests run the same cases against both
  implementations where possible.
- Azure-specific behaviour (rate limits, role propagation, OCR differences) is only seen in the
  proof run, so that run is scripted end to end and its log is kept.
