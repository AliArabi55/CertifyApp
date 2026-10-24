@description('Globally unique web app name (becomes <name>.azurewebsites.net).')
param webAppName string

param location string = resourceGroup().location

@allowed(['B1', 'B2', 'S1', 'P0v3'])
param skuName string = 'B1'

@description('Login username for the app.')
param appUsername string = 'admin'

@secure()
@description('Login password for the app. The app has no user accounts, so this protects it.')
param appPassword string

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${webAppName}-plan'
  location: location
  kind: 'linux'
  sku: {
    name: skuName
  }
  properties: {
    reserved: true
  }
}

resource site 'Microsoft.Web/sites@2023-12-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'bash startup.sh'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      http20Enabled: true
      healthCheckPath: '/health'
      appSettings: [
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'WEBSITES_PORT', value: '8000' }
        // /home is persistent storage on Linux App Service.
        { name: 'CERTIFY_DATA_DIR', value: '/home/certify/projects' }
        { name: 'CERTIFY_CONFIG_DIR', value: '/home/certify/config' }
        { name: 'CERTIFY_USERNAME', value: appUsername }
        { name: 'CERTIFY_PASSWORD', value: appPassword }
      ]
    }
  }
}

output url string = 'https://${site.properties.defaultHostName}'
