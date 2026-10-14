#!/usr/bin/env bash
# The single Azure proof run (ADR 0006): deploy, process the dataset, record results, tear down.
#
#   1. Deploy infra/main.bicep into a new resource group; the signed-in user gets data access.
#   2. OCR every sheet and title block with Document Intelligence prebuilt-read (free F0 tier).
#   3. Run extraction three ways: Azure OCR + rules, Azure OCR + gpt-4.1-mini, and local OCR +
#      gpt-4.1-mini (separating the OCR's effect from the model's).
#   4. Load the model run into the Cosmos DB register and run the register checks.
#   5. Save evidence to docs/azure-proof/, then delete the resource group and purge the soft-deleted
#      AI accounts. KEEP=1 skips the teardown.
#
# Cost: Document Intelligence F0 and the Cosmos DB free tier are free; gpt-4.1-mini is about 1M
# tokens for the two model runs, under USD 1.
#
# Usage: scripts/azure-proof.sh [location]     (default australiaeast)
set -euo pipefail

LOCATION="${1:-australiaeast}"
GROUP="${GROUP:-rg-revisa-proof}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROOF="$ROOT/docs/azure-proof"
mkdir -p "$PROOF"
cd "$ROOT"
exec > >(tee "$PROOF/transcript.txt") 2>&1

step() { printf '\n=== %s (%s)\n' "$1" "$(date +%H:%M:%S)"; }

teardown() {
  if [[ "${KEEP:-0}" == "1" ]]; then
    echo "KEEP=1: leaving $GROUP in place"
    return
  fi
  step "Tear down $GROUP"
  accounts="$(az cognitiveservices account list -g "$GROUP" --query '[].name' -o tsv 2>/dev/null || true)"
  az group delete --name "$GROUP" --yes || true
  # Deleted AI accounts are retained for 48 hours unless purged.
  while read -r account; do
    [[ -n "$account" ]] && az cognitiveservices account purge --name "$account" -g "$GROUP" --location "$LOCATION" || true
  done <<< "$accounts"
  echo "Resource group still exists: $(az group exists --name "$GROUP")"
}
trap teardown EXIT

step "Account"
az account show --query '{subscription:name, state:state}' -o tsv
me="$(az ad signed-in-user show --query id -o tsv)"

step "Deploy infra/main.bicep to $GROUP ($LOCATION)"
az group create --name "$GROUP" --location "$LOCATION" --tags project=revisa purpose=proof -o none
params="$(mktemp)"
printf '{"dataPrincipals": {"value": ["%s"]}}' "$me" > "$params"
outputs="$(az deployment group create -g "$GROUP" --template-file infra/main.bicep \
  --parameters "@$params" --query properties.outputs -o json)"
output() { python -c "import json,sys; print(json.load(sys.stdin)['$1']['value'])" <<< "$outputs"; }
export REVISA_AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT="$(output documentIntelligenceEndpoint)"
export REVISA_AZURE_OPENAI_ENDPOINT="$(output openaiEndpoint)"
export REVISA_AZURE_OPENAI_DEPLOYMENT="$(output modelDeployment)"
export REVISA_AZURE_COSMOS_ENDPOINT="$(output cosmosEndpoint)"
az resource list -g "$GROUP" --query '[].{name:name, type:type, sku:sku.name}' -o table | tee "$PROOF/resources.txt"

step "Wait for role assignments to reach the data planes"
uv run --no-sync python scripts/wait_for_access.py

step "Document Intelligence OCR"
uv run --no-sync revisa ocr-pages --engine azure
uv run --no-sync revisa ocr-blocks --engine azure

step "Extraction runs"
uv run --no-sync revisa run azure-rules --ocr azure --reader rules
uv run --no-sync revisa run azure-gpt41mini --ocr azure --reader llm+rules --llm azure
uv run --no-sync revisa run rapidocr-gpt41mini --ocr rapidocr --reader llm+rules --llm azure

step "Register in Cosmos DB"
register() { uv run --no-sync revisa register --store cosmos "$@"; }
register load evals/results/azure-gpt41mini.json | tee "$PROOF/register-load.txt"
register check | tee "$PROOF/register-check.txt"
register review | tee "$PROOF/register-review.txt"
register export > "$PROOF/register.csv"
