# 0005. Keyless access to Azure services

- Status: Accepted
- Date: 2026-10-14

## Context

API keys for Storage, Document Intelligence, Azure OpenAI and Cosmos DB would have to be
stored, rotated, and kept out of logs and source control. A leaked key grants access with no
identity attached.

## Decision

Disable local (key) authentication on every service. The app runs as a managed identity; a
developer uses `az login`. Access is granted with the narrowest built-in Entra roles per
service (Blob/Queue Data Contributor, Cognitive Services User, Cognitive Services OpenAI User,
Cosmos DB Built-in Data Contributor), declared in Bicep.

## Consequences

- No secrets exist to leak; every call is attributable to an identity.
- Setup needs role assignments, and role propagation can take a few minutes after deployment.
- Local development against Azure requires `az login` with an account that has the roles.
