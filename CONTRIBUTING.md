# Contributing

## Setup

```bash
uv sync                      # Python 3.11, all dependencies from the lockfile
uv run pre-commit install    # pre-commit and commit-msg hooks
uv run revisa dataset-download
```

## Workflow

1. Branch from `main`: `feat/<short-name>`, `fix/<short-name>`, `docs/<short-name>`.
2. Make one logical change per pull request. If a change needs a design decision, add an
   [ADR](docs/adr/README.md) in the same pull request.
3. Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/)
   (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `perf:`, `build:`, `ci:`, `chore:`, and
   `eval:` for changes to evaluation data or results). The commit-msg hook enforces this.
4. Open a pull request using the template. `main` is protected: changes land only through a
   pull request, every CI job must pass, and history stays linear: squash for small changes,
   rebase when the individual commits are worth keeping.

## Quality gates

These run on every commit (pre-commit) and every pull request (CI). None of them may be skipped
or weakened in a pull request without an ADR explaining why.

| Gate | Command |
|---|---|
| Lint, including security rules | `uv run ruff check src tests scripts` |
| Formatting | `uv run ruff format --check src tests scripts` |
| Types | `uv run mypy` (strict) |
| Tests, coverage at least 85% | `uv run pytest --cov` |
| Known-vulnerable dependencies | `uv export --no-emit-project --format requirements-txt > r.txt && uvx pip-audit -r r.txt --strict --disable-pip` |
| Secrets | gitleaks (pre-commit and CI) |
| Infrastructure | `az bicep lint --file infra/main.bicep` |

## Evaluation changes

Labels in `datasets/habs/labels.jsonl` are ground truth. A label may only change to match what
is printed on the sheet, never to match model output, and every change is listed in
`datasets/habs/README.md` with its reason. Evaluation results are committed alongside the code
that produced them.

## Tests

- Unit tests must not touch the network or a model server. Use the fakes in `tests/`.
- Tests that need live services are marked `@pytest.mark.integration` and skipped unless the
  service is configured.
