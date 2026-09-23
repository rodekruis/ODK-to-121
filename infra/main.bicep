// Container Apps Job that runs the pipeline on a schedule.
// Deploy once by hand; the GitHub workflow only swaps the image tag afterwards.

@description('Name of the Container Apps Job.')
param jobName string

@description('Resource id of an existing Container Apps environment.')
param containerAppsEnvironmentId string

@description('Name of the container registry holding the image.')
param registryName string

@description('Resource group of the container registry, if it is not this one.')
param registryResourceGroupName string = resourceGroup().name

@description('Image repository and tag, e.g. odk-to-121:abc1234.')
param image string

@description('Key Vault holding the ODK and 121 credentials.')
param keyVaultName string

@description('Application Insights resource the job ships its logs to.')
param appInsightsName string

@description('Which environment of the YAML config to run.')
@allowed(['test', 'prod'])
param pipelineEnvironment string = 'prod'

@description('Cron schedule, in UTC. Default: every 15 minutes.')
param cronExpression string = '*/15 * * * *'

@description('''
Seconds a run may take before it is killed. Keep it below the cron interval: a run that overruns is
killed rather than left to overlap with the next one, which would make both try to create the same
registrations. Killing mid-run is safe, everything already loaded is skipped next time.
''')
param replicaTimeout int = 840

param location string = resourceGroup().location

var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${jobName}-identity'
  location: location
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: registryName
  scope: resourceGroup(registryResourceGroupName)
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' existing = {
  name: appInsightsName
}

resource keyVaultAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identity.id, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      keyVaultSecretsUserRoleId
    )
  }
}

module registryAccess 'modules/registry-access.bicep' = {
  name: 'registry-access'
  scope: resourceGroup(registryResourceGroupName)
  params: {
    registryName: registryName
    principalId: identity.properties.principalId
  }
}

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: jobName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    environmentId: containerAppsEnvironmentId
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: replicaTimeout
      // Exit 1 means registrations were rejected; retrying only re-hits the same rejections and
      // doubles the alerts. The next scheduled run retries them for free.
      replicaRetryLimit: 0
      scheduleTriggerConfig: {
        cronExpression: cronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: [
        {
          name: 'appinsights-connection-string'
          value: appInsights.properties.ConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'pipeline'
          image: '${registry.properties.loginServer}/${image}'
          args: [
            '--config'
            'src/odk_to_121/configs/registrations.yaml'
            '--environment'
            pipelineEnvironment
          ]
          env: [
            {
              name: 'AZURE_KEY_VAULT_URL'
              value: keyVault.properties.vaultUri
            }
            {
              // Name fixed by the Azure SDK: DefaultAzureCredential reads it to pick the identity.
              name: 'AZURE_CLIENT_ID'
              value: identity.properties.clientId
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
        }
      ]
    }
  }
  dependsOn: [keyVaultAccess, registryAccess]
}

output jobName string = job.name
output identityClientId string = identity.properties.clientId
