@description('Azure region')
param location string

@description('Base project name')
param projectName string

@description('Environment name')
param environment string

@description('Principal ID to grant Cognitive Services OpenAI User role')
param deployerPrincipalId string = ''

var aiName = '${projectName}-${environment}'

// Cognitive Services OpenAI User built-in role
var cognitiveServicesOpenAIUserRole = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource aiServices 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: aiName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: aiName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
  tags: {
    project: projectName
    environment: environment
  }
}

resource gpt4o 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: aiServices
  name: 'gpt-4o'
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
  }
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployerPrincipalId)) {
  scope: aiServices
  name: guid(aiServices.id, deployerPrincipalId, cognitiveServicesOpenAIUserRole)
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      cognitiveServicesOpenAIUserRole
    )
    principalId: deployerPrincipalId
    principalType: 'User'
  }
}

output endpoint string = aiServices.properties.endpoint
output resourceName string = aiServices.name
