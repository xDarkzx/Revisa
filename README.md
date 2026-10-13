# Revisa

Reads the title blocks of construction drawings, keeps the drawing register, and sends anything
it isn't sure about to a person, with the evidence highlighted.

[![CI](https://github.com/xDarkzx/Revisa/actions/workflows/ci.yml/badge.svg)](https://github.com/xDarkzx/Revisa/actions/workflows/ci.yml)

> **Status: in progress.** Dataset, OCR and title-block location are done. Field extraction,
> evaluation results, the register and the Azure proof run are being built. This README will
> lead with measured results once they exist.

## Why

On a construction project, drawings arrive in batches of tens to hundreds of sheets, each
revised many times. A document controller reads every title block and types it into the
register. Mistakes mean people build from superseded drawings. See [docs/design.md](docs/design.md).

## Data

200 photographed construction drawings from 200 different buildings, public domain (Historic
American Buildings Survey, via Wikimedia Commons). The repo commits the manifest with
provenance; a command downloads the images ([ADR 0002](docs/adr/0002-public-domain-evaluation-data.md)).

## Decisions

Design decisions are recorded as [ADRs](docs/adr/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, workflow and quality gates, and
[SECURITY.md](SECURITY.md) for reporting vulnerabilities.

## Licence

Code: MIT. Drawings: public domain (Library of Congress, HABS/HAER).
