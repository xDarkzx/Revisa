// Revisa data plane: Document Intelligence, Azure OpenAI and Cosmos DB, exactly what the code uses.
// Keyless throughout: every service has local (key) auth disabled and access is granted with
// Entra ID role assignments to the identities listed in `dataPrincipals`.

targetScope = 'resourceGroup'

@minLength(3)
@maxLength(10)
param name string = 'revisa'

param location string = resourceGroup().location

@description('Entra object IDs (users or managed identities) that read and write data.')
param dataPrincipals array

@description('Principal type for dataPrincipals entries: User or ServicePrincipal.')
param dataPrincipalType string = 'User'

@allowed(['F0', 'S0'])
@description('F0 is free (500 pages/month); S0 is pay per page.')
param documentIntelligenceSku string = 'F0'

@description('Chat model that assigns OCR lines to fields (it reads text, not images).')
param modelName string = 'gpt-4.1-mini'
param modelVersion string = '2025-04-14'
@description('Thousands of tokens per minute.')
param modelCapacity int = 50

@description('Cosmos DB free tier: one account per subscription gets 1000 RU/s and 25 GB free.')
param cosmosFreeTier bool = true

var suffix = uniqueString(resourceGroup().id, name)

// Built-in role definition IDs (public, identical in every tenant).
var roles = {
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
}
var cosmosDataContributor = '00000000-0000-0000-0000-000000000002' // Cosmos DB built-in data role

resource docIntel 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${name}-di-${suffix}'
  location: location
  kind: 'FormRecognizer'
  sku: { name: documentIntelligenceSku }
  properties: {
    customSubDomainName: '${name}-di-${suffix}' // required for Entra ID auth
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource openai 'Microsoft.CognitiveServices/accounts@2023-05-01' = {
  name: '${name}-ai-${suffix}'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  properties: {
    customSubDomainName: '${name}-ai-${suffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openai
  name: modelName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: { format: 'OpenAI', name: modelName, version: modelVersion }
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: '${name}-db-${suffix}'
  location: location
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableFreeTier: cosmosFreeTier
    disableLocalAuth: true
    locations: [{ locationName: location, failoverPriority: 0 }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmos
  name: 'revisa'
  properties: {
    resource: { id: 'revisa' }
    options: { throughput: 400 } // shared by all containers; inside the free tier
  }
}

resource sheetsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: database
  name: 'sheets'
  properties: {
    resource: {
      id: 'sheets'
      partitionKey: { paths: ['/project'], kind: 'Hash' }
    }
  }
}

resource docIntelRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in dataPrincipals: {
  scope: docIntel
  name: guid(docIntel.id, p, roles.cognitiveServicesUser)
  properties: {
    principalId: p
    principalType: dataPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser)
  }
}]

resource openaiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in dataPrincipals: {
  scope: openai
  name: guid(openai.id, p, roles.cognitiveServicesOpenAIUser)
  properties: {
    principalId: p
    principalType: dataPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser)
  }
}]

resource cosmosRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = [for p in dataPrincipals: {
  parent: cosmos
  name: guid(cosmos.id, p, cosmosDataContributor)
  properties: {
    principalId: p
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosDataContributor}'
    scope: cosmos.id
  }
}]

output documentIntelligenceEndpoint string = docIntel.properties.endpoint
output openaiEndpoint string = 'https://${openai.properties.customSubDomainName}.openai.azure.com/'
output modelDeployment string = modelDeployment.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
