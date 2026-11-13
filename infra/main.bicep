@description('Globally unique web app name (becomes <name>.azurewebsites.net).')
param webAppName string

param location string = resourceGroup().location

@allowed(['B1', 'B2', 'S1', 'P0v3'])
param skuName string = 'B1'

@description('Email that becomes the owner account and inherits pre-existing projects.')
param ownerEmail string

@description('Gmail address that sends account verification and password-reset emails.')
param mailFrom string

@secure()
@description('Gmail App Password for the sender address.')
param mailAppPassword string

@secure()
@description('Fernet key (urlsafe base64, 32 bytes) used to encrypt users Gmail credentials.')
param credentialKey string

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
        { name: 'CERTIFY_AUTH_DB', value: '/home/certify/accounts.sqlite3' }
        { name: 'CERTIFY_PUBLIC_ORIGIN', value: 'https://${webAppName}.azurewebsites.net' }
        { name: 'CERTIFY_OWNER_EMAIL', value: ownerEmail }
        { name: 'CERTIFY_MAIL_FROM', value: mailFrom }
        { name: 'CERTIFY_MAIL_APP_PASSWORD', value: mailAppPassword }
        { name: 'CERTIFY_CREDENTIAL_KEY', value: credentialKey }
      ]
    }
  }
}

output url string = 'https://${site.properties.defaultHostName}'
