// Revisa data plane: storage, Document Intelligence, Azure OpenAI, Cosmos DB.
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

param visionModelName string = 'gpt-4.1-mini'
param visionModelVersion string = '2025-04-14'
@description('Thousands of tokens per minute.')
param visionModelCapacity int = 50

@description('Cosmos DB free tier: one account per subscription gets 1000 RU/s and 25 GB free.')
param cosmosFreeTier bool = true

var suffix = uniqueString(resourceGroup().id, name)

// Built-in role definition IDs (public, identical in every tenant).
var roles = {
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
}
var cosmosDataContributor = '00000000-0000-0000-0000-000000000002' // Cosmos DB built-in data role

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('${name}st${suffix}', 24)
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource inbox 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'inbox'
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource sheetQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = {
  parent: queueService
  name: 'sheets'
}

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

resource visionDeployment 'Microsoft.CognitiveServices/accounts/deployments@2023-05-01' = {
  parent: openai
  name: visionModelName
  sku: { name: 'GlobalStandard', capacity: visionModelCapacity }
  properties: {
    model: { format: 'OpenAI', name: visionModelName, version: visionModelVersion }
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

resource blobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in dataPrincipals: {
  scope: storage
  name: guid(storage.id, p, roles.storageBlobDataContributor)
  properties: {
    principalId: p
    principalType: dataPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
  }
}]

resource queueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for p in dataPrincipals: {
  scope: storage
  name: guid(storage.id, p, roles.storageQueueDataContributor)
  properties: {
    principalId: p
    principalType: dataPrincipalType
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor)
  }
}]

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

output storageAccount string = storage.name
output blobEndpoint string = storage.properties.primaryEndpoints.blob
output queueEndpoint string = storage.properties.primaryEndpoints.queue
output documentIntelligenceEndpoint string = docIntel.properties.endpoint
output openaiEndpoint string = openai.properties.endpoint
output visionDeployment string = visionDeployment.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
