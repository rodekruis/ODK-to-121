// Grants one role on a container registry. A separate module because the registry may live in
// another resource group, and a role assignment must be deployed at the scope of its target.

@description('Name of the container registry, in this module\'s resource group.')
param registryName string

@description('Principal id of the identity being granted access.')
param principalId string

@description('Id of the built-in role to grant.')
param roleDefinitionId string

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
}

resource registryAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, principalId, roleDefinitionId)
  scope: registry
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      roleDefinitionId
    )
  }
}
