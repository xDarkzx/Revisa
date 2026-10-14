# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Label audit: a blind second reading of 20 random test sheets agreed on 130 of 140 values;
  four label values were corrected from the sheet, rule 5 (dates) was clarified, and all runs
  were re-scored from cached responses. Test-half date accuracy is now 32% (gpt-4.1-mini on
  Document Intelligence) and 30% (rules on Document Intelligence).

## [0.1.0] - 2026-10-14

### Added

- Dataset tooling: collects public-domain photographed construction drawings from Wikimedia
  Commons (1,406 sheets), samples 200 from 200 building records, and records provenance.
- Ground-truth labels for all 200 sheets, with labelling rules, provenance and a fixed dev/test
  split (ADR 0008).
- OCR behind one interface: RapidOCR locally, Document Intelligence `prebuilt-read` in Azure.
- Title-block location from OCR keywords (ADR 0004), and a second OCR pass on the enlarged crop.
- Construction pack: date parsing, rules for drawing number, date, scale and sheet n of m, a
  largest-lettering title baseline, value coercion and scoring.
- Language-model reader that answers with OCR line ids; values not on the cited lines are
  rejected and counted (ADR 0003, ADR 0007). Works with Ollama and Azure OpenAI; responses
  are cached per sheet.
- Routing of every sheet to accepted or needs review, with reasons; two readers cross-check.
- Evaluation per field, per sheet and for routing; `revisa run` and `revisa report`.
- Drawing register with SQLite and Cosmos DB stores; checks for superseded revisions,
  duplicates, missing sheets and set-size conflicts; `revisa register`.
- Azure infrastructure (Bicep, keyless): Document Intelligence F0, Azure OpenAI gpt-4.1-mini,
  Cosmos DB free tier. `scripts/azure-proof.sh` deploys, runs and tears down once.
- Architecture decision records 0001-0008; pack specifications for medical referrals and
  supplier invoices.
- Contribution guide, security policy, issue and pull request templates, Dependabot, CI with
  lint, strict types, coverage gate, dependency audit, secret scan, Bicep and shell checks.

### Changed

- Infrastructure no longer includes the storage account and queue, which no code used yet.
