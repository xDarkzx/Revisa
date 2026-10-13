# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[GitHub security advisories](https://github.com/xDarkzx/Revisa/security/advisories/new), not
in a public issue. You'll get an acknowledgement within five working days.

## Design measures

- **No stored credentials.** Azure services run with key authentication disabled; the app uses
  a managed identity and Entra ID role assignments ([ADR 0005](docs/adr/0005-keyless-azure-access.md)).
- **Least privilege.** Each identity gets only the data-plane roles it needs, declared in
  `infra/main.bicep`.
- **Untrusted input.** Uploaded drawings and OCR text are treated as untrusted. OCR text is
  passed to the language model as data inside a delimited block, and the model can only choose
  among OCR line IDs, so injected instructions can't produce values that aren't on the sheet.
- **Supply chain.** Dependencies are locked (`uv.lock`), audited for known vulnerabilities in
  CI, and updated by Dependabot. Secrets scanning runs on every commit.

## Supported versions

Only `main` is supported.
