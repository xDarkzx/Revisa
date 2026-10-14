# Azure proof run, 2026-10-14

The single deployment described in [ADR 0006](../adr/0006-local-first-single-azure-proof.md):
`scripts/azure-proof.sh` deployed `infra/main.bicep` to a new resource group, processed all 200
sheets, loaded the register into Cosmos DB, and deleted everything. Total wall time 47 minutes.

| Time (NZDT) | Step |
|---|---|
| 13:35 | Deploy `rg-revisa-proof` in Australia East (2.5 minutes) |
| 13:38 | Role assignments reached all three data planes within 5 seconds |
| 13:38 | Document Intelligence `prebuilt-read`: 200 pages, then 150 title-block crops, paced for the free tier |
| 14:14 | Three extraction runs (Azure OCR + rules, Azure OCR + gpt-4.1-mini, local OCR + gpt-4.1-mini) |
| 14:22 | 200 sheets upserted into Cosmos DB; register checks and review queue read back from it |
| 14:22 | Resource group deleted; AI accounts purged |

## What was deployed

| Resource | SKU | Notes |
|---|---|---|
| Document Intelligence | F0 (free) | key auth disabled |
| AI Services + `gpt-4.1-mini` deployment | S0, GlobalStandard 50K TPM | key auth disabled |
| Cosmos DB for NoSQL | free tier, 400 RU/s shared | key auth disabled, container partitioned by `/project` |

Every call used Entra ID tokens from the signed-in Azure CLI user; no key or connection string
existed at any point. The signed-in user got data-plane roles only for the run's lifetime.

## Cost

Document Intelligence F0 and the Cosmos DB free tier are free. The two gpt-4.1-mini runs used
383,658 prompt tokens and 29,617 completion tokens in 263 calls, about US$0.20 at list price.

## Files

| File | Contents |
|---|---|
| [transcript.txt](transcript.txt) | Full console output of the run, including per-sheet OCR progress |
| [resources.txt](resources.txt) | Resources in the group after deployment |
| [register-load.txt](register-load.txt), [register-check.txt](register-check.txt), [register-review.txt](register-review.txt) | Register commands run against Cosmos DB |
| [register.csv](register.csv) | The register as exported from Cosmos DB |
| [../../evals/results](../../evals/results) | `azure-rules`, `azure-gpt41mini`, `rapidocr-gpt41mini`: per-sheet values, sources, evidence line ids, outcomes, usage |

## Things the run surfaced

- **Purge timing.** Purging the Document Intelligence account straight after the group delete
  returned `Bad Request`; it was purged by hand a minute later and the subscription verified
  empty (no groups, resources or soft-deleted accounts). The script now retries the purge.
- **Missing-sheet false positive.** The register reported "1 of 1 sheets not in the register"
  for a sheet whose own number wasn't read. Fixed afterwards; `register-check.txt` is left as
  recorded.
- **An OCR year of 1077.** One date was parsed as December 1077 from a misread "1977". Dates
  outside 1700-2100 are now rejected.

The results in `evals/results` were re-scored after these fixes from the cached OCR and model
responses (no further Azure calls); git history holds the files exactly as the run wrote them.
