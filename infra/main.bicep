targetScope = 'subscription'

@description('Environment name (dev, prod, etc.)')
param environment string = 'dev'

@description('Azure region for all resources')
param location string = 'eastus2'

@description('Base name for the project')
param projectName string = 'agent-harness'

@description('Principal ID to grant data-plane access (from `az ad signed-in-user show --query id`)')
param deployerPrincipalId string = ''

var rgName = 'rg-${projectName}-${environment}'

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: rgName
  location: location
  tags: {
    project: projectName
    environment: environment
    managedBy: 'bicep'
  }
}

module ai 'modules/ai.bicep' = {
  scope: rg
  name: 'ai-${environment}'
  params: {
    location: location
    projectName: projectName
    environment: environment
    deployerPrincipalId: deployerPrincipalId
  }
}

output resourceGroupName string = rg.name
output aiEndpoint string = ai.outputs.endpoint
output aiResourceName string = ai.outputs.resourceName
