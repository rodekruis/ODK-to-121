// Identity GitHub Actions uses to build the image and repoint the job.
// Deploy once, AFTER main.bicep: the role assignment below needs the job to exist.

@description('Name of the Container Apps Job the workflow repoints.')
param jobName string

@description('Name of the container registry the workflow pushes to.')
param registryName string

@description('Resource group of the container registry, if it is not this one.')
param registryResourceGroupName string = resourceGroup().name

@description('''
Subject of the GitHub OIDC token. Copy it verbatim from the `subject claim` line that azure/login
prints. The rodekruis organisation uses immutable identifiers, so it reads
repo:rodekruis@20355963/ODK-to-121@1356060218:environment:prod rather than repo:org/repo:...
A mismatch is accepted at deployment time and only fails later, at token exchange.
''')
param githubSubject string

param location string = resourceGroup().location

// Contributor, not AcrPush: `az acr build` schedules an ACR Task, which AcrPush does not cover.
var contributorRoleId = 'b24988ac-6180-42a0-ab88-20f7382dd24c'

// Also grants listSecrets and start; see the note in the README.
var jobsContributorRoleId = '4e3d2b60-56ae-4dc6-a233-09c8e5a82e68'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${jobName}-deployer'
  location: location
}

resource githubTrust 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2023-01-31' = {
  name: 'github-prod'
  parent: identity
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: githubSubject
    audiences: ['api://AzureADTokenExchange']
  }
}

resource job 'Microsoft.App/jobs@2024-03-01' existing = {
  name: jobName
}

resource jobAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(job.id, identity.id, jobsContributorRoleId)
  scope: job
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      jobsContributorRoleId
    )
  }
}

module registryAccess 'modules/registry-access.bicep' = {
  name: 'deployer-registry-access'
  scope: resourceGroup(registryResourceGroupName)
  params: {
    registryName: registryName
    principalId: identity.properties.principalId
    roleDefinitionId: contributorRoleId
  }
}

@description('Store as the AZURE_DEPLOYER_CLIENT_ID secret on the prod GitHub environment.')
output deployerClientId string = identity.properties.clientId
